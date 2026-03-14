import base64
import json
import os
import secrets
from   osbot_utils.type_safe.Type_Safe             import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto            import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto              import PKI__Crypto
from   sg_send_cli.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path

BARE_KEYS_DIR = os.path.join('bare', 'keys')


class Vault__Key_Manager(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto
    pki        : PKI__Crypto

    def generate_branch_key_pair(self):
        return self.pki.generate_signing_key_pair()

    def generate_key_id(self) -> str:
        return 'key-' + secrets.token_hex(8)

    def store_public_key(self, key_id: str, public_key, read_key: bytes) -> None:
        pem  = self.pki.export_public_key_pem(public_key)
        data = json.dumps({'type': 'public', 'pem': pem}).encode()
        ciphertext = self.crypto.encrypt(read_key, data)
        path = self._key_path(key_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)

    def load_public_key(self, key_id: str, read_key: bytes):
        path       = self._key_path(key_id)
        with open(path, 'rb') as f:
            ciphertext = f.read()
        data = json.loads(self.crypto.decrypt(read_key, ciphertext))
        return self.pki.import_public_key_pem(data['pem'])

    def store_private_key(self, key_id: str, private_key, read_key: bytes) -> None:
        pem  = self.pki.export_private_key_pem(private_key)
        data = json.dumps({'type': 'private', 'pem': pem}).encode()
        ciphertext = self.crypto.encrypt(read_key, data)
        path = self._key_path(key_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)

    def load_private_key(self, key_id: str, read_key: bytes):
        path       = self._key_path(key_id)
        with open(path, 'rb') as f:
            ciphertext = f.read()
        data = json.loads(self.crypto.decrypt(read_key, ciphertext))
        return self.pki.import_private_key_pem(data['pem'])

    def store_private_key_locally(self, key_id: str, private_key, local_dir: str) -> None:
        pem  = self.pki.export_private_key_pem(private_key)
        path = os.path.join(local_dir, key_id + '.pem')
        os.makedirs(local_dir, exist_ok=True)
        with open(path, 'w') as f:
            f.write(pem)

    def load_private_key_locally(self, key_id: str, local_dir: str):
        path = os.path.join(local_dir, key_id + '.pem')
        with open(path, 'r') as f:
            pem = f.read()
        return self.pki.import_private_key_pem(pem)

    def key_exists(self, key_id: str) -> bool:
        return os.path.isfile(self._key_path(key_id))

    def list_keys(self) -> list:
        keys_dir = os.path.join(self.vault_path, BARE_KEYS_DIR)
        if not os.path.isdir(keys_dir):
            return []
        return sorted(f for f in os.listdir(keys_dir) if f.startswith('key-'))

    def _key_path(self, key_id: str) -> str:
        return os.path.join(self.vault_path, BARE_KEYS_DIR, key_id)
