import base64
import functools
import hashlib
import hmac
import os
import re
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

SALT_PREFIX             = 'sg-vault-v1'

# Vault IDs that appear in S3 paths must be short opaque alphanumeric strings.
# Human-readable IDs (containing hyphens, uppercase, spaces, or long English
# words) leak confidential information to server logs, CDN logs, and S3 ACLs.
VAULT_ID_PATTERN = re.compile(r'^[a-z0-9]{4,24}$')

@functools.lru_cache(maxsize=256)
def _pbkdf2_cached(passphrase: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm  = hashes.SHA256(),
                     length     = AES_KEY_BYTES,
                     salt       = salt,
                     iterations = PBKDF2_ITERATIONS)
    return kdf.derive(passphrase)

WRITE_SALT_PREFIX       = 'sg-vault-v1:write'
REF_DOMAIN              = 'sg-vault-v1:file-id:ref'
BRANCH_INDEX_DOMAIN     = 'sg-vault-v1:file-id:branch-index'
BRANCH_REF_DOMAIN       = 'sg-vault-v1:file-id:branch-ref'
STRUCTURE_KEY_INFO      = b'sg-vault-v1:structure-key'


class Vault__Crypto(Type_Safe):

    def parse_vault_key(self, vault_key: str) -> tuple:
        parts = vault_key.rsplit(':', 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f'Invalid vault key format: expected {{passphrase}}:{{vault_id}}')
        passphrase = parts[0]
        vault_id   = parts[1]
        if not VAULT_ID_PATTERN.match(vault_id):
            raise ValueError(
                f'Invalid vault_id "{vault_id}": must be 4-24 lowercase alphanumeric characters '
                f'with no hyphens, spaces, or uppercase. Human-readable IDs leak confidential '
                f'information to server logs and S3 paths. Use `sgit init` to generate a safe ID.'
            )
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

    def derive_ref_file_id(self, read_key: bytes, vault_id: str) -> str:
        domain = f'{REF_DOMAIN}:{vault_id}'
        return self.derive_file_id(read_key, domain)

    def derive_branch_index_file_id(self, read_key: bytes, vault_id: str) -> str:
        domain = f'{BRANCH_INDEX_DOMAIN}:{vault_id}'
        return self.derive_file_id(read_key, domain)

    def derive_branch_ref_file_id(self, read_key: bytes, vault_id: str, branch_name: str) -> str:
        domain = f'{BRANCH_REF_DOMAIN}:{vault_id}:{branch_name}'
        return self.derive_file_id(read_key, domain)

    def compute_object_id(self, ciphertext: bytes) -> str:
        raw_hash = hashlib.sha256(ciphertext).hexdigest()[:12]
        return f'obj-cas-imm-{raw_hash}'

    def derive_keys(self, passphrase: str, vault_id: str) -> dict:
        read_key_bytes        = self.derive_read_key(passphrase, vault_id)
        write_key_bytes       = self.derive_write_key(passphrase, vault_id)
        ref_file_id           = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
        branch_index_file_id  = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
        return dict(read_key_bytes        = read_key_bytes,
                    read_key              = read_key_bytes.hex(),
                    write_key_bytes       = write_key_bytes,
                    write_key             = write_key_bytes.hex(),
                    ref_file_id           = ref_file_id,
                    branch_index_file_id  = branch_index_file_id,
                    passphrase            = passphrase,
                    vault_id              = vault_id)

    def derive_keys_from_vault_key(self, vault_key: str) -> dict:
        from sgit_ai.transfer.Simple_Token import Simple_Token
        if Simple_Token.is_simple_token(vault_key):
            # Plain simple token: "word-word-NNNN"
            return self.derive_keys_from_simple_token(vault_key)
        passphrase, vault_id = self.parse_vault_key(vault_key)
        if Simple_Token.is_simple_token(passphrase):
            # Combined format: "word-word-NNNN:<hash>" — passphrase is the token
            return self.derive_keys_from_simple_token(passphrase)
        return self.derive_keys(passphrase, vault_id)

    def derive_keys_from_simple_token(self, token_str: str) -> dict:
        from sgit_ai.transfer.Simple_Token           import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        st              = Simple_Token(token=Safe_Str__Simple_Token(token_str))
        read_key_bytes  = st.read_key()
        write_key_bytes = st.write_key()
        ec_seed_bytes   = st.ec_seed()
        vault_id        = st.transfer_id()   # hash of token — safe to log in URLs
        ref_file_id           = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
        branch_index_file_id  = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
        return dict(vault_id               = vault_id,
                    read_key_bytes         = read_key_bytes,
                    read_key               = read_key_bytes.hex(),
                    write_key              = write_key_bytes.hex(),
                    write_key_bytes        = write_key_bytes,
                    ec_seed                = ec_seed_bytes,
                    ref_file_id            = ref_file_id,
                    branch_index_file_id   = branch_index_file_id)

    def import_read_key(self, read_key_hex: str, vault_id: str) -> dict:
        read_key_bytes        = bytes.fromhex(read_key_hex)
        ref_file_id           = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
        branch_index_file_id  = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
        return dict(read_key_bytes       = read_key_bytes,
                    read_key             = read_key_hex,
                    write_key            = '',
                    write_key_bytes      = None,
                    ref_file_id          = ref_file_id,
                    branch_index_file_id = branch_index_file_id,
                    vault_id             = vault_id)

    def derive_structure_key(self, read_key: bytes) -> bytes:
        """Derive a structure key from the read key using HKDF-SHA256.

        The structure key can decrypt metadata (refs, branches, trees, commits)
        but NOT blob content.  It is derived one-way from the read key so that
        holding the structure key reveals nothing about the vault key or
        content encryption key.
        """
        hkdf = HKDF(algorithm = hashes.SHA256(),
                     length    = AES_KEY_BYTES,
                     salt      = None,
                     info      = STRUCTURE_KEY_INFO)
        return hkdf.derive(read_key)

    # --- metadata encryption (for tree entry names, commit messages, etc.) ---

    def encrypt_metadata(self, read_key: bytes, plaintext: str) -> str:
        data       = plaintext.encode('utf-8')
        ciphertext = self.encrypt(read_key, data)
        return base64.b64encode(ciphertext).decode('ascii')

    def encrypt_deterministic(self, key: bytes, plaintext: bytes) -> bytes:
        """Encrypt with HMAC-derived IV so same key+plaintext always yields the same ciphertext.

        Used for tree objects and tree entry metadata so that unchanged subtrees
        produce identical object IDs across commits (true CAS deduplication).
        Blobs must continue to use random IVs via encrypt().
        """
        iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]
        return self.encrypt(key, plaintext, iv=iv)

    def encrypt_metadata_deterministic(self, key: bytes, plaintext: str) -> str:
        """Deterministic metadata encryption for tree entry fields."""
        data       = plaintext.encode('utf-8')
        ciphertext = self.encrypt_deterministic(key, data)
        return base64.b64encode(ciphertext).decode('ascii')

    def decrypt_metadata(self, read_key: bytes, b64_ciphertext: str) -> str:
        ciphertext = base64.b64decode(b64_ciphertext)
        data       = self.decrypt(read_key, ciphertext)
        return data.decode('utf-8')

    # --- low-level primitives ---

    def clear_kdf_cache(self) -> None:
        """Flush the module-level PBKDF2 LRU cache.

        Call this at natural passphrase-boundary points (end of rekey,
        end of probe, end of delete-on-remote) so that derived keys and
        passphrase bytes do not remain reachable from process memory in
        long-running agent contexts.

        The cache is module-level (not per-instance) because lru_cache
        on a free function is the only way to share it across all
        Vault__Crypto instances without a shared singleton.  Clearing it
        here is safe: subsequent derivations simply recompute and re-fill
        the cache from scratch.
        """
        _pbkdf2_cached.cache_clear()

    def derive_key_from_passphrase(self, passphrase: bytes, salt: bytes) -> bytes:
        return _pbkdf2_cached(passphrase, salt)

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

    def content_hash(self, plaintext: bytes) -> str:
        return hashlib.sha256(plaintext).hexdigest()[:12]

    def hash_data(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def generate_salt(self) -> bytes:
        return os.urandom(16)

    def generate_iv(self) -> bytes:
        return os.urandom(GCM_IV_BYTES)
