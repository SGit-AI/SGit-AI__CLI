"""Real keys for the signing tests (no mocks): generated with `cryptography`, written in
OpenSSH format, and the allowed-signers / revocation files the verifier reads."""
import os
import tempfile
from   cryptography.hazmat.primitives                     import serialization
from   cryptography.hazmat.primitives.asymmetric          import ec, rsa
from   cryptography.hazmat.primitives.asymmetric.ed25519  import Ed25519PrivateKey

KEY_MAKERS = {'ed25519'  : lambda: Ed25519PrivateKey.generate(),
              'nistp256' : lambda: ec.generate_private_key(ec.SECP256R1()),
              'nistp384' : lambda: ec.generate_private_key(ec.SECP384R1()),
              'nistp521' : lambda: ec.generate_private_key(ec.SECP521R1()),
              'rsa2048'  : lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)}


class Signing_Keys:

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='sgit-signing-')

    def make(self, kind: str = 'ed25519', name: str = None) -> tuple:
        """(private key object, private key path, OpenSSH public line)."""
        key  = KEY_MAKERS[kind]()
        path = os.path.join(self.dir, name or kind)
        with open(path, 'wb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                      serialization.NoEncryption()))
        os.chmod(path, 0o600)
        line = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
        with open(path + '.pub', 'w') as f:
            f.write(line + '\n')
        return key, path, line

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir, name)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def cleanup(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)
