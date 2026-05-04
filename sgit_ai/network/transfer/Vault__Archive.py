import io
import json
import os
import time
import zipfile
from osbot_utils.type_safe.Type_Safe                                            import Type_Safe
from sgit_ai.crypto.Vault__Crypto                                               import Vault__Crypto
from sgit_ai.schemas.Schema__Vault_Archive_Manifest                             import (
    Schema__Vault_Archive_Manifest, VAULT_ARCHIVE_SCHEMA_VERSION)
from sgit_ai.schemas.Schema__Archive_Provenance                                 import Schema__Archive_Provenance
from sgit_ai.safe_types.Safe_Str__Schema_Version                                import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Vault_Id                                      import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Key_Type                                      import Safe_Str__Key_Type
from sgit_ai.safe_types.Safe_UInt__File_Count                                   import Safe_UInt__File_Count
from sgit_ai.safe_types.Safe_UInt__File_Size                                    import Safe_UInt__File_Size
from sgit_ai.safe_types.Safe_Str__Commit_Message                                import Safe_Str__Commit_Message
from sgit_ai.safe_types.Safe_Str__Branch_Id                                     import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Object_Id                                     import Safe_Str__Object_Id
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now import Timestamp_Now

INNER_ZIP_NAME       = 'inner.zip.enc'
MANIFEST_NAME        = 'manifest.json'
DECRYPTION_KEY_NAME  = 'decryption-key.bin'

AES_KEY_BYTES = 32


class Vault__Archive(Type_Safe):
    crypto : Vault__Crypto

    def build_inner_zip(self, files: dict) -> bytes:
        """Zip {relative_path: content} dict into bytes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for path, content in sorted(files.items()):
                if isinstance(content, str):
                    content = content.encode('utf-8')
                zf.writestr(path, content)
        return buf.getvalue()

    def encrypt_inner_zip(self, inner_zip: bytes) -> tuple:
        """Generate random inner_key (32 bytes), encrypt inner_zip. Return (inner_key, inner_zip_enc)."""
        inner_key    = os.urandom(AES_KEY_BYTES)
        inner_zip_enc = self.crypto.encrypt(inner_key, inner_zip)
        return inner_key, inner_zip_enc

    def encrypt_inner_key(self, inner_key: bytes, vault_read_key: bytes) -> bytes:
        """Encrypt inner_key with vault_read_key. Return decryption_key_bin bytes."""
        return self.crypto.encrypt(vault_read_key, inner_key)

    def build_manifest(self, files: dict, inner_key_type: str,
                       vault_id: str, branch_id: str, commit_id: str,
                       description: str = '') -> bytes:
        """Build manifest.json bytes (Schema__Vault_Archive_Manifest serialized)."""
        total_bytes = sum(
            len(v.encode('utf-8') if isinstance(v, str) else v)
            for v in files.values()
        )
        provenance = Schema__Archive_Provenance(
            branch_id  = Safe_Str__Branch_Id(branch_id)  if branch_id  else None,
            commit_id  = Safe_Str__Object_Id(commit_id)  if commit_id  else None,
            author_key = None
        )
        manifest = Schema__Vault_Archive_Manifest(
            schema         = Safe_Str__Schema_Version(VAULT_ARCHIVE_SCHEMA_VERSION),
            vault_id       = Safe_Str__Vault_Id(vault_id)            if vault_id    else None,
            created_at     = Timestamp_Now(),
            files          = Safe_UInt__File_Count(len(files)),
            total_bytes    = Safe_UInt__File_Size(total_bytes),
            inner_key_type = Safe_Str__Key_Type(inner_key_type)      if inner_key_type else None,
            inner_key_id   = None,
            description    = Safe_Str__Commit_Message(description)   if description  else None,
            provenance     = provenance
        )
        return json.dumps(manifest.json(), default=str).encode('utf-8')

    def build_outer_zip(self, manifest_bytes: bytes, inner_zip_enc: bytes,
                        decryption_key_bin: bytes | None) -> bytes:
        """Assemble outer zip: manifest.json + inner.zip.enc + decryption-key.bin (if present)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME,  manifest_bytes)
            zf.writestr(INNER_ZIP_NAME, inner_zip_enc)
            if decryption_key_bin is not None:
                zf.writestr(DECRYPTION_KEY_NAME, decryption_key_bin)
        return buf.getvalue()

    def encrypt_outer_zip(self, outer_zip: bytes, token: str) -> bytes:
        """Encrypt outer_zip with Simple Token derived key. Return encrypted blob."""
        from sgit_ai.network.transfer.Simple_Token           import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        st        = Simple_Token(token=Safe_Str__Simple_Token(token))
        key_bytes = st.aes_key()
        return self.crypto.encrypt(key_bytes, outer_zip)

    def build_archive(self, files: dict, token: str,
                      vault_read_key: bytes | None,
                      vault_id: str, branch_id: str, commit_id: str,
                      description: str = '') -> bytes:
        """Full pipeline: build → encrypt → return encrypted blob.

        If vault_read_key is None, inner_key_type='none' (no inner encryption).
        """
        if vault_read_key is not None:
            inner_key_type   = 'vault_key'
            inner_key, inner_zip_enc = self.encrypt_inner_zip(self.build_inner_zip(files))
            decryption_key_bin = self.encrypt_inner_key(inner_key, vault_read_key)
        else:
            inner_key_type     = 'none'
            inner_zip_enc      = self.build_inner_zip(files)   # plain zip, no encryption
            decryption_key_bin = None

        manifest_bytes = self.build_manifest(files, inner_key_type, vault_id,
                                             branch_id, commit_id, description)
        outer_zip      = self.build_outer_zip(manifest_bytes, inner_zip_enc, decryption_key_bin)
        return self.encrypt_outer_zip(outer_zip, token)

    def decrypt_outer(self, encrypted_blob: bytes, token: str) -> tuple:
        """Decrypt outer blob, return (manifest_bytes, inner_zip_enc, decryption_key_bin_or_None)."""
        from sgit_ai.network.transfer.Simple_Token           import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        st        = Simple_Token(token=Safe_Str__Simple_Token(token))
        key_bytes = st.aes_key()
        outer_zip_bytes = self.crypto.decrypt(key_bytes, encrypted_blob)

        buf = io.BytesIO(outer_zip_bytes)
        with zipfile.ZipFile(buf, mode='r') as zf:
            manifest_bytes     = zf.read(MANIFEST_NAME)
            inner_zip_enc      = zf.read(INNER_ZIP_NAME)
            if DECRYPTION_KEY_NAME in zf.namelist():
                decryption_key_bin = zf.read(DECRYPTION_KEY_NAME)
            else:
                decryption_key_bin = None
        return manifest_bytes, inner_zip_enc, decryption_key_bin

    def decrypt_inner(self, inner_zip_enc: bytes, decryption_key_bin: bytes,
                      vault_read_key: bytes) -> bytes:
        """Decrypt inner zip. Return inner_zip_bytes."""
        inner_key       = self.crypto.decrypt(vault_read_key, decryption_key_bin)
        inner_zip_bytes = self.crypto.decrypt(inner_key, inner_zip_enc)
        return inner_zip_bytes

    def extract_files(self, inner_zip_bytes: bytes) -> dict:
        """Unzip inner zip. Return {path: content} dict."""
        files = {}
        buf   = io.BytesIO(inner_zip_bytes)
        with zipfile.ZipFile(buf, mode='r') as zf:
            for name in zf.namelist():
                files[name] = zf.read(name)
        return files
