import json
import os
from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.safe_types.Safe_Str__Vault_Path                                      import Safe_Str__Vault_Path
from sgit_ai.crypto.PKI__Crypto                                                   import PKI__Crypto


class PKI__Key_Store(Type_Safe):
    keys_dir : Safe_Str__Vault_Path = None
    crypto   : PKI__Crypto

    def generate_and_store(self, label: str, passphrase: str) -> dict:
        enc_priv, enc_pub  = self.crypto.generate_encryption_key_pair()
        sig_priv, sig_pub  = self.crypto.generate_signing_key_pair()

        enc_fingerprint = self.crypto.compute_fingerprint(enc_pub)
        sig_fingerprint = self.crypto.compute_fingerprint(sig_pub)

        key_dir = self._key_dir(enc_fingerprint)
        os.makedirs(key_dir, exist_ok=True)

        from sgit_ai.crypto.Vault__Secret_File import Vault__Secret_File
        Vault__Secret_File().write(os.path.join(key_dir, 'private_key.pem'), self.crypto.export_private_key_pem(enc_priv, passphrase))
        with open(os.path.join(key_dir, 'public_key.pem'), 'w') as f:
            f.write(self.crypto.export_public_key_pem(enc_pub))
        Vault__Secret_File().write(os.path.join(key_dir, 'signing_private.pem'), self.crypto.export_private_key_pem(sig_priv, passphrase))
        with open(os.path.join(key_dir, 'signing_public.pem'), 'w') as f:
            f.write(self.crypto.export_public_key_pem(sig_pub))

        metadata = dict(label                  = label,
                        algorithm              = 'RSA-OAEP',
                        key_size               = 4096,
                        encryption_fingerprint = enc_fingerprint,
                        signing_fingerprint    = sig_fingerprint,
                        created                = int(Timestamp_Now()))
        with open(os.path.join(key_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)

        return metadata

    def list_keys(self) -> list:
        keys_dir = str(self.keys_dir) if self.keys_dir else ''
        if not keys_dir or not os.path.isdir(keys_dir):
            return []
        result = []
        for entry in sorted(os.listdir(keys_dir)):
            meta_path = os.path.join(keys_dir, entry, 'metadata.json')
            if os.path.isfile(meta_path):
                with open(meta_path, 'r') as f:
                    result.append(json.load(f))
        return result

    def load_key_pair(self, fingerprint: str, passphrase: str) -> dict:
        key_dir = self._key_dir(fingerprint)
        if not os.path.isdir(key_dir):
            return None

        with open(os.path.join(key_dir, 'private_key.pem'), 'r') as f:
            enc_priv = self.crypto.import_private_key_pem(f.read(), passphrase)
        with open(os.path.join(key_dir, 'public_key.pem'), 'r') as f:
            enc_pub = self.crypto.import_public_key_pem(f.read())
        with open(os.path.join(key_dir, 'signing_private.pem'), 'r') as f:
            sig_priv = self.crypto.import_private_key_pem(f.read(), passphrase)
        with open(os.path.join(key_dir, 'signing_public.pem'), 'r') as f:
            sig_pub = self.crypto.import_public_key_pem(f.read())
        with open(os.path.join(key_dir, 'metadata.json'), 'r') as f:
            metadata = json.load(f)

        return dict(encryption_private = enc_priv,
                    encryption_public  = enc_pub,
                    signing_private    = sig_priv,
                    signing_public     = sig_pub,
                    metadata           = metadata)

    def export_public_bundle(self, fingerprint: str) -> dict:
        key_dir = self._key_dir(fingerprint)
        if not os.path.isdir(key_dir):
            return None

        with open(os.path.join(key_dir, 'public_key.pem'), 'r') as f:
            enc_pem = f.read()
        with open(os.path.join(key_dir, 'signing_public.pem'), 'r') as f:
            sig_pem = f.read()
        with open(os.path.join(key_dir, 'metadata.json'), 'r') as f:
            metadata = json.load(f)

        return dict(v       = 1,
                    encrypt = enc_pem,
                    sign    = sig_pem,
                    label   = metadata.get('label', ''),
                    fingerprint         = metadata['encryption_fingerprint'],
                    signing_fingerprint = metadata['signing_fingerprint'])

    def delete_key(self, fingerprint: str) -> bool:
        key_dir  = self._key_dir(fingerprint)
        keys_dir = os.path.realpath(str(self.keys_dir))
        if os.path.realpath(os.path.dirname(key_dir)) != keys_dir:        # belt and braces: never above keys_dir
            raise ValueError(f'refusing to delete outside the key store: {fingerprint!r}')
        if not os.path.isdir(key_dir):
            return False
        import shutil
        shutil.rmtree(key_dir)
        return True

    def _key_dir(self, fingerprint: str) -> str:
        """The folder for one key. The fingerprint is validated before any path is built:
        TM-F32 — `sgit pki delete ..` used to rmtree the parent of the key store."""
        safe_name = self.safe_fingerprint(fingerprint).replace(':', '_')
        return os.path.join(str(self.keys_dir), safe_name)

    def safe_fingerprint(self, fingerprint) -> str:
        from sgit_ai.safe_types.Safe_Str__Key_Fingerprint import Safe_Str__Key_Fingerprint
        value = str(Safe_Str__Key_Fingerprint(str(fingerprint or '')))            # raises on any other shape
        if not value:
            raise ValueError('a key fingerprint is required (sha256:<16 hex>)')
        return value
