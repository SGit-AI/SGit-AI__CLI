import json
import os
from datetime                                      import datetime, timezone
from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path

SECRETS_SALT_PREFIX = 'sg-send-secrets-v1'


class Secrets__Store(Type_Safe):
    store_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto

    def derive_master_key(self, passphrase: str) -> bytes:
        salt = f'{SECRETS_SALT_PREFIX}:master'.encode()
        return self.crypto.derive_key_from_passphrase(passphrase.encode(), salt)

    def store(self, passphrase: str, key: str, value: str) -> None:
        master_key = self.derive_master_key(passphrase)
        secrets    = self._load_all(master_key)
        secrets[key] = dict(value      = value,
                            created_at = datetime.now(timezone.utc).isoformat())
        self._save_all(master_key, secrets)

    def get(self, passphrase: str, key: str) -> str:
        master_key = self.derive_master_key(passphrase)
        secrets    = self._load_all(master_key)
        entry      = secrets.get(key)
        if entry is None:
            return None
        return entry['value']

    def list_keys(self, passphrase: str) -> list:
        master_key = self.derive_master_key(passphrase)
        secrets    = self._load_all(master_key)
        return sorted(secrets.keys())

    def delete(self, passphrase: str, key: str) -> bool:
        master_key = self.derive_master_key(passphrase)
        secrets    = self._load_all(master_key)
        if key not in secrets:
            return False
        del secrets[key]
        self._save_all(master_key, secrets)
        return True

    def _load_all(self, master_key: bytes) -> dict:
        store_path = str(self.store_path) if self.store_path else self.store_path
        if not store_path or not os.path.isfile(store_path):
            return {}
        with open(store_path, 'rb') as f:
            encrypted = f.read()
        if not encrypted:
            return {}
        plaintext = self.crypto.decrypt(master_key, encrypted)
        return json.loads(plaintext.decode('utf-8'))

    def _save_all(self, master_key: bytes, secrets: dict) -> None:
        store_path = str(self.store_path) if self.store_path else self.store_path
        plaintext  = json.dumps(secrets, indent=2).encode('utf-8')
        encrypted  = self.crypto.encrypt(master_key, plaintext)
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        with open(store_path, 'wb') as f:
            f.write(encrypted)
