"""Helpers for the pack-mode tests: a counting in-memory host, small vault builders
and a working-copy snapshot, all on disk and in process (hermetic)."""
import os
import tempfile

from sgit_ai.core.Vault__Sync                   import Vault__Sync
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory


class Host__Counting(Vault__API__In_Memory):
    """Every call counted; every file id asked for recorded, so a test can prove a
    pack vault's client never asks the host for a loose object."""

    def setup(self):
        super().setup()
        self.calls           = dict(list_files=0, batch_read=0, read=0, read_large=0, write=0, batch=0, delete=0, read_range=0)
        self.range_bytes     = 0
        self.range_reads     = []
        self.requested_ids   = []
        self.written_ids     = []
        self.batch_reads     = []           # one list of file ids per batch_read call
        self.listed_prefixes = []
        return self

    def reset_counts(self):
        for k in self.calls:
            self.calls[k] = 0
        self.requested_ids   = []
        self.written_ids     = []
        self.batch_reads     = []
        self.listed_prefixes = []
        self.range_bytes     = 0
        self.range_reads     = []           # (file id, start, end) per ranged read

    def requests(self) -> int:
        return sum(self.calls.values())

    def list_files(self, vault_id, prefix=''):
        self.calls['list_files'] += 1
        self.listed_prefixes.append(prefix)
        return super().list_files(vault_id, prefix)

    def batch_read(self, vault_id, file_ids, failures=None):
        self.calls['batch_read'] += 1
        self.requested_ids.extend(file_ids)
        self.batch_reads.append(list(file_ids))
        return super().batch_read(vault_id, file_ids, failures=failures)

    def read(self, vault_id, file_id):
        self.calls['read'] += 1
        self.requested_ids.append(file_id)
        return super().read(vault_id, file_id)

    def read_range(self, vault_id, file_id, start, end):
        self.calls['read_range'] += 1
        self.requested_ids.append(file_id)
        data = super().read_range(vault_id, file_id, start, end)
        self.range_bytes += len(data)
        self.range_reads.append((file_id, int(start), int(end)))
        return data

    def read_large(self, vault_id, file_id, size=None):
        self.calls['read_large'] += 1
        self.requested_ids.append(file_id)
        return super().read(vault_id, file_id)

    def write(self, vault_id, file_id, write_key, payload):
        self.calls['write'] += 1
        self.written_ids.append(file_id)
        return super().write(vault_id, file_id, write_key, payload)

    def batch(self, vault_id, write_key, operations):
        self.calls['batch'] += 1
        for op in operations:
            if op.get('op', 'write') == 'read':
                self.requested_ids.append(op['file_id'])
            elif op.get('op', 'write') == 'write':
                self.written_ids.append(op['file_id'])
        return super().batch(vault_id, write_key, operations)

    def delete(self, vault_id, file_id, write_key):
        self.calls['delete'] += 1
        return super().delete(vault_id, file_id, write_key)

    def host_files(self, vault_id: str) -> dict:
        prefix = f'{vault_id}/'
        return {k[len(prefix):]: v for k, v in self._store.items() if k.startswith(prefix)}

    def loose_objects(self, vault_id: str) -> list:
        return sorted(k for k in self.host_files(vault_id) if k.startswith('bare/data/'))

    def packs(self, vault_id: str, folder: str = 'bare/packs/') -> list:
        return sorted(k for k in self.host_files(vault_id) if k.startswith(folder))


class Pack__Env:
    """Vaults for one test, on disk under a temp root; a fresh Vault__Sync per clone."""

    def __init__(self, api=None):
        self.api  = api or Host__Counting().setup()
        self.root = tempfile.mkdtemp(prefix='sgit-pack-')
        self.n    = 0

    def sync(self) -> Vault__Sync:
        return Vault__Sync(crypto=Vault__Crypto(), api=self.api)

    def path(self, name: str = None) -> str:
        self.n += 1
        return os.path.join(self.root, name or f'v{self.n}')

    def write(self, directory: str, files: dict) -> None:
        for rel, content in files.items():
            full = os.path.join(directory, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb' if isinstance(content, bytes) else 'w') as f:
                f.write(content)

    def delete(self, directory: str, rel: str) -> None:
        os.remove(os.path.join(directory, rel))

    def tree(self, directory: str) -> dict:
        """{relative path: bytes} of the working copy (the vault's own folder excluded)."""
        out = {}
        for base, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != '.sg_vault']
            for name in files:
                full = os.path.join(base, name)
                with open(full, 'rb') as f:
                    out[os.path.relpath(full, directory).replace(os.sep, '/')] = f.read()
        return out

    def store_bytes(self, directory: str) -> dict:
        data_dir = os.path.join(directory, '.sg_vault', 'bare', 'data')
        out = {}
        for name in os.listdir(data_dir) if os.path.isdir(data_dir) else []:
            with open(os.path.join(data_dir, name), 'rb') as f:
                out[name] = f.read()
        return out

    def text_files(self, n: int, prefix: str = 'f', size: int = 2000, salt: str = '') -> dict:
        """n distinct, compressible text files (prose-like, so deflate bites)."""
        files = {}
        for i in range(n):
            line = f'{salt}line {i}: the quick brown fox jumps over the lazy dog number {i}\n'
            files[f'{prefix}{i}.md'] = (line * (size // len(line) + 1))[:size].encode()
        return files

    def pack_vault(self, files: dict = None, vault_key=None, message='first') -> tuple:
        """init --packs, write, commit, push. Returns (sync, directory, vault_key)."""
        sync      = self.sync()
        directory = self.path()
        created   = sync.init(directory, vault_key=vault_key, packs=True)
        if files:
            self.write(directory, files)
            sync.commit(directory, message=message)
        sync.push(directory)
        return sync, directory, created['vault_key']

    def normal_vault(self, files: dict = None, vault_key=None, message='first') -> tuple:
        sync      = self.sync()
        directory = self.path()
        created   = sync.init(directory, vault_key=vault_key)
        if files:
            self.write(directory, files)
            sync.commit(directory, message=message)
        sync.push(directory)
        return sync, directory, created['vault_key']

    def clone(self, vault_key: str, name: str = None, **kwargs) -> tuple:
        sync      = self.sync()
        directory = self.path(name)
        sync.clone(vault_key, directory, **kwargs)
        return sync, directory
