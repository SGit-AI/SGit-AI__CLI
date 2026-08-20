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
CACHE_VALUE_DOMAIN      = 'sg-vault-v1:file-id:cache-value'
CACHE_POINTER_DOMAIN    = 'sg-vault-v1:file-id:cache-pointer'
STRUCTURE_KEY_INFO      = b'sg-vault-v1:structure-key'

# Self-identifying key prefixes (design contract 08/14, naming revised 08/17).
# The value AFTER the prefix is byte-identical to the legacy key, so key
# material, derivation and every stored artifact are unchanged — the prefix
# exists purely so secret scanners, git hooks and humans can recognise a key,
# and its INTENT, on sight. Old sgit / SG-Vault versions work by stripping it.
#
# The names are semantic rather than coded because that buys three things a
# code like `rk1` cannot:
#   * ONE scanner rule covers every private credential — `sgit_private_\S+` —
#     including private key types that do not exist yet;
#   * the rule is version-independent: a future `sgit_private_read2_` still
#     matches, where `rk1` -> `rk2` would silently stop matching;
#   * public and private differ by a WORD, not by one character, so a typo or
#     a tired reviewer cannot flip a published key into a leak alarm (or worse,
#     the reverse).
# Underscores (not hyphens) keep a whole key selectable by double-click.
VAULT_KEY_PREFIX        = 'sgit_private_vault_'   # read AND write capability
READ_KEY_PREFIX         = 'sgit_private_read_'    # read-only, keep secret
READ_KEY_PUBLIC_PREFIX  = 'sgit_public_read_'     # read-only, deliberately published

# Released briefly in v0.15.5. Accepted on input forever, never emitted again.
LEGACY_VAULT_KEY_PREFIX = 'sgit_vk1_'
LEGACY_READ_KEY_PREFIX  = 'sgit_rk1_'

KEY_PREFIXES            = (VAULT_KEY_PREFIX, READ_KEY_PREFIX, READ_KEY_PUBLIC_PREFIX,
                           LEGACY_VAULT_KEY_PREFIX, LEGACY_READ_KEY_PREFIX)
VAULT_KEY_PREFIXES      = (VAULT_KEY_PREFIX, LEGACY_VAULT_KEY_PREFIX)
READ_KEY_PREFIXES       = (READ_KEY_PREFIX, READ_KEY_PUBLIC_PREFIX, LEGACY_READ_KEY_PREFIX)


class Vault__Crypto(Type_Safe):

    # --- key prefixes -------------------------------------------------------

    def strip_key_prefix(self, key: str) -> str:
        """Remove a self-identifying prefix, if present. Accepts every current
        and legacy prefix plus bare keys — the single normalisation point for
        key input, so no caller ever has to know the prefix list."""
        key = (key or '').strip()
        for prefix in KEY_PREFIXES:
            if key.startswith(prefix):
                return key[len(prefix):]
        return key

    def classify_key(self, key: str) -> 'Enum__Key_Kind':
        """What does this credential DECLARE itself to be?

        Classification is by declaration, never by shape — guessing from shape
        is what once misrouted a 64-hex passphrase to a read-only clone. This is
        the primitive a loader page mirrors to refuse a vault key: a read-only
        surface must never accept write capability just because someone pasted
        it. Bare/legacy-format keys are UNKNOWN and resolved by context.
        """
        from sgit_ai.safe_types.Enum__Key_Kind import Enum__Key_Kind
        key = (key or '').strip()
        if key.startswith(READ_KEY_PUBLIC_PREFIX):
            return Enum__Key_Kind.READ_PUBLIC
        if key.startswith(READ_KEY_PREFIX) or key.startswith(LEGACY_READ_KEY_PREFIX):
            return Enum__Key_Kind.READ_PRIVATE
        if key.startswith(VAULT_KEY_PREFIX) or key.startswith(LEGACY_VAULT_KEY_PREFIX):
            return Enum__Key_Kind.VAULT
        return Enum__Key_Kind.UNKNOWN

    def format_vault_key(self, vault_key: str) -> str:
        """Display/storage form of a vault key:
        sgit_private_vault_{passphrase}:{vault_id}. Idempotent; upgrades legacy."""
        vault_key = self.strip_key_prefix(vault_key)
        return f'{VAULT_KEY_PREFIX}{vault_key}'

    def format_read_key(self, read_key_hex: str, public: bool = False) -> str:
        """Display form of a read key. Idempotent; upgrades legacy prefixes.

        `public=True` marks a key that is DELIBERATELY published (a static
        "public vault" loader page). Same bytes, different declaration — so a
        secret scanner alerting on `sgit_private_` stays meaningful instead of
        being trained into noise by every intentionally-open vault.
        """
        read_key_hex = self.strip_key_prefix(str(read_key_hex or ''))
        prefix       = READ_KEY_PUBLIC_PREFIX if public else READ_KEY_PREFIX
        return f'{prefix}{read_key_hex}'

    def parse_vault_key(self, vault_key: str) -> tuple:
        vault_key = self.strip_key_prefix(vault_key)
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

    def derive_cache_value_file_id(self, read_key: bytes, vault_id: str, path: str) -> str:
        """12-hex tail for a value cache at `path`. Cache-layer contract 08/12 v0 §4.

        `path` is the RAW vault-relative path string (byte-identical to a flatten()
        key), NOT a sanitised Safe_Str, so all runtimes derive the same id. Callers
        assemble the full id as `cch-pid-{mutability}-{tail}` (the mutability label is
        not hashed). Same key rule as every file id: `read_key` only — never write_key.
        """
        domain = f'{CACHE_VALUE_DOMAIN}:{vault_id}:{path}'
        return self.derive_file_id(read_key, domain)

    def derive_cache_pointer_file_id(self, read_key: bytes, vault_id: str, path: str) -> str:
        """12-hex tail for a pointer cache at `path`. Cache-layer contract 08/12 v0 §4.

        Independent namespace from the value cache (kind is part of the domain), so the
        same path yields two unrelated ids. See derive_cache_value_file_id for the
        raw-path and assembly rules.
        """
        domain = f'{CACHE_POINTER_DOMAIN}:{vault_id}:{path}'
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
        passphrase, vault_id = self.parse_vault_key(vault_key)
        return self.derive_keys(passphrase, vault_id)

    def import_read_key(self, read_key_hex: str, vault_id: str) -> dict:
        read_key_hex          = self.strip_key_prefix(read_key_hex)
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
        """Flush the module-level PBKDF2 LRU cache to reduce key material residency in memory."""
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
