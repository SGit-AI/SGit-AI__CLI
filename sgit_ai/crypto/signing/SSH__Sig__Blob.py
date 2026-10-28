"""SSH__Sig__Blob — the SSHSIG format (OpenSSH PROTOCOL.sshsig), parsed and built.

    "SSHSIG" | uint32 1 | string publickey | string namespace | string reserved
             | string hash_algorithm | string signature

The key signs  "SSHSIG" | string namespace | string reserved | string hash_algorithm
| string H(message). Parsing is strict (design__02 §5.4.1): exact magic, version 1,
a size cap, no trailing bytes; the namespace and hash are checked by the verifier."""
import base64
import hashlib
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.signing.SSH__Wire             import SSH__Wire, Vault__SSH_Format_Error

MAGIC          = b'SSHSIG'
SIG_VERSION    = 1
MAX_BLOB_BYTES = 6144
HASHES         = {'sha256': hashlib.sha256, 'sha512': hashlib.sha512}
ARMOR_BEGIN    = '-----BEGIN SSH SIGNATURE-----'
ARMOR_END      = '-----END SSH SIGNATURE-----'
ARMOR_COLUMNS  = 70


class SSH__Sig__Blob(Type_Safe):
    public_key_blob : bytes
    namespace       : bytes
    reserved        : bytes
    hash_algorithm  : bytes
    signature_blob  : bytes

    def parse(self, blob: bytes) -> 'SSH__Sig__Blob':
        if len(blob) > MAX_BLOB_BYTES:
            raise Vault__SSH_Format_Error(f'SSHSIG of {len(blob)} bytes is over the {MAX_BLOB_BYTES}-byte cap')
        wire = SSH__Wire(data=blob)
        if wire.read_bytes(len(MAGIC)) != MAGIC:
            raise Vault__SSH_Format_Error('not an SSHSIG (wrong magic)')
        version = wire.read_uint32()
        if version != SIG_VERSION:
            raise Vault__SSH_Format_Error(f'SSHSIG version {version} (only 1 is defined)')
        self.public_key_blob = wire.read_string()
        self.namespace       = wire.read_string()
        self.reserved        = wire.read_string()
        self.hash_algorithm  = wire.read_string()
        self.signature_blob  = wire.read_string()
        wire.expect_end('SSHSIG')
        return self

    def build(self) -> bytes:
        w = SSH__Wire()
        return (MAGIC + w.uint32(SIG_VERSION) + w.string(self.public_key_blob) + w.string(self.namespace) +
                w.string(self.reserved) + w.string(self.hash_algorithm) + w.string(self.signature_blob))

    def message_hash(self, payload: bytes) -> bytes:
        hasher = HASHES.get(self.hash_algorithm.decode('ascii', 'replace'))
        if hasher is None:
            raise Vault__SSH_Format_Error(f'hash {self.hash_algorithm!r} is not sha256 or sha512')
        return hasher(payload).digest()

    def signed_data(self, payload: bytes) -> bytes:
        """The bytes the key signs for `payload`."""
        w = SSH__Wire()
        return (MAGIC + w.string(self.namespace) + w.string(self.reserved) + w.string(self.hash_algorithm) +
                w.string(self.message_hash(payload)))

    def armor(self, blob: bytes) -> str:
        text = base64.b64encode(blob).decode()
        rows = [text[i:i + ARMOR_COLUMNS] for i in range(0, len(text), ARMOR_COLUMNS)]
        return '\n'.join([ARMOR_BEGIN] + rows + [ARMOR_END]) + '\n'

    def dearmor(self, text: str) -> bytes:
        lines = [line.strip() for line in text.strip().splitlines()]
        if not lines or lines[0] != ARMOR_BEGIN or lines[-1] != ARMOR_END:
            raise Vault__SSH_Format_Error('not an armored SSH signature')
        try:
            return base64.b64decode(''.join(lines[1:-1]), validate=True)
        except ValueError as e:
            raise Vault__SSH_Format_Error(f'armored SSH signature is not base64: {e}') from None
