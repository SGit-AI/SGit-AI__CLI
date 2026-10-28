"""SSH__Revocation_List — Git's gpg.ssh.revocationFile: public-key lines, or a binary
KRL (which only ssh-keygen reads: the caller delegates when is_krl())."""
import base64
from   osbot_utils.type_safe.Type_Safe              import Type_Safe

KRL_MAGIC = b'SSHKRL\n\x00'


class SSH__Revocation_List(Type_Safe):
    revoked : list[bytes]                                   # wire key blobs
    krl     : bool = False

    def load(self, path: str) -> 'SSH__Revocation_List':
        with open(path, 'rb') as f:
            data = f.read()
        if data.startswith(KRL_MAGIC):
            self.krl = True
            return self
        for line in data.decode('utf-8', 'replace').splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and not parts[0].startswith('#'):
                try:
                    self.revoked.append(base64.b64decode(parts[1], validate=True))
                except ValueError:
                    continue
        return self

    def is_krl(self) -> bool:
        return self.krl

    def is_revoked(self, key_blob: bytes) -> bool:
        return key_blob in self.revoked
