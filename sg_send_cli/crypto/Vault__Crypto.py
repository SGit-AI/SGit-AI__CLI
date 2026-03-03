import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf     import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2   import PBKDF2HMAC
from cryptography.hazmat.primitives               import hashes
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Vault_Key   import Safe_Str__Vault_Key

PBKDF2_ITERATIONS = 600_000
AES_KEY_BYTES     = 32
GCM_IV_BYTES      = 12
GCM_TAG_BYTES     = 16
HKDF_INFO_PREFIX  = b'sg-send-file-key'


class Vault__Crypto(Type_Safe):

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
