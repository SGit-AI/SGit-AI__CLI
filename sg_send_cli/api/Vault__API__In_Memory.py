import base64
import hashlib

from sg_send_cli.api.Vault__API import Vault__API


class Vault__API__In_Memory(Vault__API):
    """In-memory API implementation for testing and local development.

    Stores all vault data in a Python dict instead of hitting a remote server.
    Supports the full Vault__API surface: write, read, delete, batch, list_files.
    """

    def setup(self):
        self._store       = {}
        self._write_count = 0
        self._batch_count = 0
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        self._store[f'{vault_id}/{file_id}'] = payload
        self._write_count += 1
        return {'status': 'ok'}

    def read(self, vault_id: str, file_id: str) -> bytes:
        key = f'{vault_id}/{file_id}'
        if key not in self._store:
            raise RuntimeError(f'Not found: {key}')
        return self._store[key]

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        key = f'{vault_id}/{file_id}'
        self._store.pop(key, None)
        return {'status': 'ok'}

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        self._batch_count += 1
        results = []
        for op in operations:
            op_type = op.get('op', 'write')
            file_id = op['file_id']
            key     = f'{vault_id}/{file_id}'

            if op_type == 'delete':
                self._store.pop(key, None)
                results.append({'status': 'ok'})

            elif op_type == 'write-if-match':
                current_hash = ''
                if key in self._store:
                    current_hash = hashlib.sha256(self._store[key]).hexdigest()
                expected = op.get('match', '')
                if expected and current_hash != expected:
                    return {'status': 'conflict', 'message': f'CAS mismatch on {file_id}'}
                data = base64.b64decode(op['data'])
                self._store[key] = data
                results.append({'status': 'ok'})

            else:
                data = base64.b64decode(op['data'])
                self._store[key] = data
                results.append({'status': 'ok'})

        return {'status': 'ok', 'results': results}

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        full_prefix = f'{vault_id}/{prefix}'
        return [k.replace(f'{vault_id}/', '', 1)
                for k in self._store
                if k.startswith(full_prefix)]
