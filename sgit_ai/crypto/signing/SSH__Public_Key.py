"""SSH__Public_Key — an SSH public key in wire form: fingerprint, display type, and
in-process signature verification with `cryptography` (design__02 §5.4.3).

ssh-ed25519, ecdsa-sha2-nistp256/384/521, ssh-rsa (rsa-sha2-256/512 signatures only:
the SHA-1 `ssh-rsa` signature is refused, as ssh-keygen refuses it), and the FIDO
types sk-ssh-ed25519@openssh.com / sk-ecdsa-sha2-nistp256@openssh.com, whose
signatures cover SHA256(application) | flags | counter | SHA256(data) (PROTOCOL.u2f).
Certificates are not verified here: the caller delegates them to ssh-keygen."""
import base64
import hashlib
from   cryptography.exceptions                                 import InvalidSignature
from   cryptography.hazmat.primitives                          import hashes
from   cryptography.hazmat.primitives.asymmetric               import ec, padding
from   cryptography.hazmat.primitives.asymmetric.ed25519       import Ed25519PublicKey
from   cryptography.hazmat.primitives.asymmetric.rsa           import RSAPublicNumbers
from   cryptography.hazmat.primitives.asymmetric.utils         import encode_dss_signature
from   osbot_utils.type_safe.Type_Safe                         import Type_Safe
from   sgit_ai.crypto.signing.SSH__Wire                        import SSH__Wire, Vault__SSH_Format_Error

ED25519     = 'ssh-ed25519'
RSA         = 'ssh-rsa'
SK_ED25519  = 'sk-ssh-ed25519@openssh.com'
SK_ECDSA    = 'sk-ecdsa-sha2-nistp256@openssh.com'
ECDSA       = {'ecdsa-sha2-nistp256': (ec.SECP256R1, hashes.SHA256, 'nistp256'),
               'ecdsa-sha2-nistp384': (ec.SECP384R1, hashes.SHA384, 'nistp384'),
               'ecdsa-sha2-nistp521': (ec.SECP521R1, hashes.SHA512, 'nistp521')}
RSA_SIGS    = {'rsa-sha2-256': hashes.SHA256, 'rsa-sha2-512': hashes.SHA512}
DISPLAY     = {ED25519: 'ED25519', RSA: 'RSA', SK_ED25519: 'ED25519-SK', SK_ECDSA: 'ECDSA-SK',
               **{name: 'ECDSA' for name in ECDSA}}
FLAG_USER_PRESENT  = 0x01
FLAG_USER_VERIFIED = 0x04
MIN_RSA_BITS       = 1024                                   # ssh-keygen's floor (SSH_RSA_MINIMUM_MODULUS_SIZE)


class SSH__Public_Key(Type_Safe):
    blob : bytes                                            # the wire public key

    def from_openssh_line(self, line: str) -> 'SSH__Public_Key':
        """`<type> <base64> [comment]` (an authorized_keys / .pub line)."""
        parts = line.strip().split()
        if len(parts) < 2:
            raise Vault__SSH_Format_Error('not an OpenSSH public key line')
        try:
            self.blob = base64.b64decode(parts[1], validate=True)
        except ValueError:
            raise Vault__SSH_Format_Error('OpenSSH public key is not base64') from None
        if self.algorithm() != parts[0]:
            raise Vault__SSH_Format_Error(f'key type {parts[0]} does not match the key ({self.algorithm()})')
        return self

    def algorithm(self) -> str:
        return SSH__Wire(data=self.blob).read_string().decode('ascii', 'replace')

    def is_certificate(self) -> bool:
        return self.algorithm().endswith('-cert-v01@openssh.com')

    def fingerprint(self) -> str:
        """As `ssh-keygen -l` prints it."""
        return 'SHA256:' + base64.b64encode(hashlib.sha256(self.blob).digest()).decode().rstrip('=')

    def display_type(self) -> str:
        return DISPLAY.get(self.algorithm(), self.algorithm().upper()[:32])

    def openssh_line(self) -> str:
        return f'{self.algorithm()} {base64.b64encode(self.blob).decode()}'

    # --- verifying ----------------------------------------------------------------

    def verify(self, signature_blob: bytes, data: bytes, require_presence: bool = True,
               require_verification: bool = False) -> bool:
        """True when `signature_blob` (an SSH signature: string algorithm, then its blob)
        is this key's over `data`. Any malformed input is False, never an exception."""
        try:
            return self._verify(signature_blob, data, require_presence, require_verification)
        except (Vault__SSH_Format_Error, InvalidSignature, ValueError, TypeError):
            return False

    def _verify(self, signature_blob: bytes, data: bytes, require_presence: bool, require_verification: bool) -> bool:
        key       = SSH__Wire(data=self.blob)
        key_type  = key.read_string().decode('ascii', 'replace')
        sig       = SSH__Wire(data=signature_blob)
        sig_type  = sig.read_string().decode('ascii', 'replace')
        if key_type == ED25519:
            public = key.read_string()
            key.expect_end('key')
            if sig_type != ED25519:
                return False
            raw = sig.read_string()
            sig.expect_end('signature')
            Ed25519PublicKey.from_public_bytes(public).verify(raw, data)
            return True
        if key_type in ECDSA:
            curve, digest, curve_name = ECDSA[key_type]
            if key.read_string().decode('ascii', 'replace') != curve_name or sig_type != key_type:
                return False
            point = key.read_string()
            key.expect_end('key')
            der   = self._ecdsa_der(sig.read_string())
            sig.expect_end('signature')
            ec.EllipticCurvePublicKey.from_encoded_point(curve(), point).verify(der, data, ec.ECDSA(digest()))
            return True
        if key_type == RSA:
            e, n = key.read_mpint(), key.read_mpint()
            key.expect_end('key')
            if sig_type not in RSA_SIGS or n.bit_length() < MIN_RSA_BITS:
                return False                                            # ssh-rsa (SHA-1) never accepted
            raw = sig.read_string()
            sig.expect_end('signature')
            RSAPublicNumbers(e, n).public_key().verify(raw, data, padding.PKCS1v15(), RSA_SIGS[sig_type]())
            return True
        if key_type in (SK_ED25519, SK_ECDSA):
            return self._verify_sk(key, key_type, sig, sig_type, data, require_presence, require_verification)
        return False                                                    # ssh-dss, certificates, unknown

    def _verify_sk(self, key, key_type, sig, sig_type, data, require_presence, require_verification) -> bool:
        if sig_type != key_type:
            return False
        if key_type == SK_ED25519:
            public      = key.read_string()
            application = key.read_string()
            key.expect_end('key')
            raw         = sig.read_string()
        else:
            if key.read_string() != b'nistp256':
                return False
            point       = key.read_string()
            application = key.read_string()
            key.expect_end('key')
            raw         = self._ecdsa_der(sig.read_string())
        flags   = sig.read_byte()
        counter = sig.read_uint32()
        sig.expect_end('signature')
        if require_presence and not flags & FLAG_USER_PRESENT:
            return False
        if require_verification and not flags & FLAG_USER_VERIFIED:
            return False
        message = (hashlib.sha256(application).digest() + bytes([flags]) + counter.to_bytes(4, 'big') +
                   hashlib.sha256(data).digest())
        if key_type == SK_ED25519:
            Ed25519PublicKey.from_public_bytes(public).verify(raw, message)
        else:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point).verify(raw, message, ec.ECDSA(hashes.SHA256()))
        return True

    def _ecdsa_der(self, inner: bytes) -> bytes:
        wire = SSH__Wire(data=inner)
        r, s = wire.read_mpint(), wire.read_mpint()
        wire.expect_end('ECDSA signature')
        return encode_dss_signature(r, s)
