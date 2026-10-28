"""SSH__Signer__In_Process — `ssh-keygen -Y sign -n git` without ssh-keygen, for an
unencrypted OpenSSH private-key file (design__02 D4: Windows and minimal containers;
also what the tests sign with). Produces the same SSHSIG as ssh-keygen: ed25519
signatures are deterministic, so the blob is byte-identical (checked against a
signature ssh-keygen made, in the tests). Hash sha512, as ssh-keygen's default;
RSA signs with rsa-sha2-512, as ssh-keygen does."""
import base64
from   cryptography.hazmat.primitives                          import hashes, serialization
from   cryptography.hazmat.primitives.asymmetric               import ec, padding, rsa
from   cryptography.hazmat.primitives.asymmetric.ed25519       import Ed25519PrivateKey
from   cryptography.hazmat.primitives.asymmetric.utils         import decode_dss_signature
from   osbot_utils.type_safe.Type_Safe                         import Type_Safe
from   sgit_ai.crypto.signing.SSH__Public_Key                  import SSH__Public_Key, ECDSA
from   sgit_ai.crypto.signing.SSH__Sig__Blob                   import SSH__Sig__Blob
from   sgit_ai.crypto.signing.SSH__Wire                        import SSH__Wire, Vault__SSH_Format_Error
from   sgit_ai.safe_types.Enum__User_Signature_Format          import Enum__User_Signature_Format
from   sgit_ai.schemas.Schema__User_Signature                  import Schema__User_Signature

NAMESPACE = b'git'
HASH      = b'sha512'


class SSH__Signer__In_Process(Type_Safe):

    def load_key(self, key_path: str):
        with open(key_path, 'rb') as f:
            data = f.read()
        try:
            return serialization.load_ssh_private_key(data, password=None)
        except (ValueError, TypeError) as e:
            raise Vault__SSH_Format_Error(f'cannot sign in-process with {key_path}: {e} '
                                          f'(an encrypted key needs ssh-keygen or ssh-agent)') from None

    def public_key(self, private_key) -> SSH__Public_Key:
        line = private_key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                     serialization.PublicFormat.OpenSSH).decode()
        return SSH__Public_Key().from_openssh_line(line)

    def sign(self, payload: bytes, key_path: str) -> Schema__User_Signature:
        return Schema__User_Signature(format=Enum__User_Signature_Format.SSH,
                                      blob=base64.b64encode(self.sign_blob(payload, self.load_key(key_path))).decode())

    def sign_blob(self, payload: bytes, private_key) -> bytes:
        public = self.public_key(private_key)
        sshsig = SSH__Sig__Blob(public_key_blob=public.blob, namespace=NAMESPACE, reserved=b'', hash_algorithm=HASH)
        data   = sshsig.signed_data(payload)
        sshsig.signature_blob = self.signature(private_key, public.algorithm(), data)
        return sshsig.build()

    def signature(self, private_key, algorithm: str, data: bytes) -> bytes:
        wire = SSH__Wire()
        if isinstance(private_key, Ed25519PrivateKey):
            return wire.string(b'ssh-ed25519') + wire.string(private_key.sign(data))
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            digest = ECDSA[algorithm][1]
            r, s   = decode_dss_signature(private_key.sign(data, ec.ECDSA(digest())))
            return wire.string(algorithm.encode()) + wire.string(wire.mpint(r) + wire.mpint(s))
        if isinstance(private_key, rsa.RSAPrivateKey):
            raw = private_key.sign(data, padding.PKCS1v15(), hashes.SHA512())
            return wire.string(b'rsa-sha2-512') + wire.string(raw)
        raise Vault__SSH_Format_Error(f'cannot sign in-process with a {algorithm} key')
