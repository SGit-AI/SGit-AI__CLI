import hashlib
import hmac
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf     import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2   import PBKDF2HMAC
from cryptography.hazmat.primitives               import hashes
from osbot_utils.type_safe.Type_Safe              import Type_Safe

PBKDF2_ITERATIONS = 600_000
AES_KEY_BYTES     = 32
GCM_IV_BYTES      = 12
GCM_TAG_BYTES     = 16
HKDF_INFO_PREFIX  = b'sg-send-file-key'

SALT_PREFIX       = 'sg-vault-v1'
WRITE_SALT_PREFIX = 'sg-vault-v1:write'
TREE_DOMAIN       = 'sg-vault-v1:file-id:tree'
SETTINGS_DOMAIN   = 'sg-vault-v1:file-id:settings'
REF_DOMAIN        = 'sg-vault-v1:file-id:ref'


class Vault__Crypto(Type_Safe):

    def parse_vault_key(self, vault_key: str) -> tuple:
        parts = vault_key.rsplit(':', 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f'Invalid vault key format: expected {{passphrase}}:{{vault_id}}')
        passphrase = parts[0]
        vault_id   = parts[1]
        return passphrase, vault_id

    def derive_read_key(self, passphrase: str, vault_id: str) -> bytes:
        salt = f'{SALT_PREFIX}:{vault_id}'.encode()
        return self.derive_key_from_passphrase(passphrase.encode(), salt)

    def derive_write_key(self, passphrase: str, vault_id: str) -> bytes:
        salt = f'{WRITE_SALT_PREFIX}:{vault_id}'.encode()
        return self.derive_key_from_passphrase(passphrase.encode(), salt)

    def derive_file_id(self, read_key: bytes, domain_string: str) -> str:
        mac = hmac.new(read_key, domain_string.encode(), hashlib.sha256).hexdigest()
        return mac[:12]

    def derive_tree_file_id(self, read_key: bytes, vault_id: str) -> str:
        domain = f'{TREE_DOMAIN}:{vault_id}'
        return self.derive_file_id(read_key, domain)

    def derive_settings_file_id(self, read_key: bytes, vault_id: str) -> str:
        domain = f'{SETTINGS_DOMAIN}:{vault_id}'
        return self.derive_file_id(read_key, domain)

    def derive_ref_file_id(self, read_key: bytes, vault_id: str) -> str:
        domain = f'{REF_DOMAIN}:{vault_id}'
        return self.derive_file_id(read_key, domain)

    def compute_object_id(self, ciphertext: bytes) -> str:
        return hashlib.sha256(ciphertext).hexdigest()[:12]

    def derive_keys(self, passphrase: str, vault_id: str) -> dict:
        read_key_bytes   = self.derive_read_key(passphrase, vault_id)
        write_key_bytes  = self.derive_write_key(passphrase, vault_id)
        tree_file_id     = self.derive_tree_file_id(read_key_bytes, vault_id)
        settings_file_id = self.derive_settings_file_id(read_key_bytes, vault_id)
        ref_file_id      = self.derive_ref_file_id(read_key_bytes, vault_id)
        return dict(read_key_bytes   = read_key_bytes,
                    read_key         = read_key_bytes.hex(),
                    write_key_bytes  = write_key_bytes,
                    write_key        = write_key_bytes.hex(),
                    tree_file_id     = tree_file_id,
                    settings_file_id = settings_file_id,
                    ref_file_id      = ref_file_id,
                    passphrase       = passphrase,
                    vault_id         = vault_id)

    def derive_keys_from_vault_key(self, vault_key: str) -> dict:
        passphrase, vault_id = self.parse_vault_key(vault_key)
        return self.derive_keys(passphrase, vault_id)

    # --- low-level primitives ---

    def derive_key_from_passphrase(self, passphrase: bytes, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm  = hashes.SHA256(),
                         length     = AES_KEY_BYTES,
                         salt       = salt,
                         iterations = PBKDF2_ITERATIONS)
        return kdf.derive(passphrase)

    def derive_file_key(self, vault_key: bytes, file_context: bytes) -> bytes:
        hkdf = HKDF(algorithm = hashes.SHA256(),
                     length    = AES_KEY_BYTES,
                     salt      = None,
                     info      = HKDF_INFO_PREFIX + file_context)
        return hkdf.derive(vault_key)

    def encrypt(self, key: bytes, plaintext: bytes, iv: bytes = None) -> bytes:
        if iv is None:
            iv = os.urandom(GCM_IV_BYTES)
        aesgcm     = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        return iv + ciphertext

    def decrypt(self, key: bytes, data: bytes) -> bytes:
        iv         = data[:GCM_IV_BYTES]
        ciphertext = data[GCM_IV_BYTES:]
        aesgcm     = AESGCM(key)
        return aesgcm.decrypt(iv, ciphertext, None)

    def hash_data(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def generate_salt(self) -> bytes:
        return os.urandom(16)

    def generate_iv(self) -> bytes:
        return os.urandom(GCM_IV_BYTES)
