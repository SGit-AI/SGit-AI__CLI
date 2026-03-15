import base64
import json
import os
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sg_send_cli.crypto.Vault__Crypto            import Vault__Crypto
from sg_send_cli.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path

REFS_DIR      = 'refs'
HEAD_FILE     = 'head'
BARE_REFS_DIR = os.path.join('bare', 'refs')


class Vault__Ref_Manager(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None
    crypto     : Vault__Crypto        = None
    use_v2     : bool                 = False

    # --- v1 API (backward compatible) ---

    def read_head(self) -> str:
        path = self._head_path()
        if not os.path.isfile(path):
            return None
        with open(path, 'r') as f:
            commit_id = f.read().strip()
        return commit_id if commit_id else None

    def write_head(self, commit_id: str) -> None:
        path = self._head_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(commit_id)

    def is_initialized(self) -> bool:
        if self.use_v2:
            refs_dir = os.path.join(self.vault_path, BARE_REFS_DIR)
            return os.path.isdir(refs_dir) and len(self.list_refs()) > 0
        return os.path.isfile(self._head_path())

    # --- v2 API (encrypted multi-ref) ---

    def write_ref(self, ref_id: str, commit_id: str, read_key: bytes = None) -> None:
        path = self._ref_path(ref_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if read_key and self.crypto:
            data       = json.dumps({'commit_id': commit_id}).encode()
            ciphertext = self.crypto.encrypt(read_key, data)
            with open(path, 'wb') as f:
                f.write(ciphertext)
        else:
            with open(path, 'w') as f:
                f.write(commit_id)

    def read_ref(self, ref_id: str, read_key: bytes = None) -> str:
        path = self._ref_path(ref_id)
        if not os.path.isfile(path):
            return None
        if read_key and self.crypto:
            with open(path, 'rb') as f:
                ciphertext = f.read()
            data = json.loads(self.crypto.decrypt(read_key, ciphertext))
            return data.get('commit_id')
        else:
            with open(path, 'r') as f:
                return f.read().strip()

    def list_refs(self) -> list[str]:
        refs_dir = os.path.join(self.vault_path, BARE_REFS_DIR)
        if not os.path.isdir(refs_dir):
            return []
        return sorted(f for f in os.listdir(refs_dir) if f.startswith('ref-'))

    def ref_exists(self, ref_id: str) -> bool:
        return os.path.isfile(self._ref_path(ref_id))

    def encrypt_ref_value(self, commit_id: str, read_key: bytes) -> bytes:
        """Encrypt a commit_id for storage as a ref, returning raw ciphertext bytes."""
        data = json.dumps({'commit_id': commit_id}).encode()
        return self.crypto.encrypt(read_key, data)

    def get_ref_file_hash(self, ref_id: str) -> str:
        """Return base64-encoded raw content of the ref file (for write-if-match CAS).

        The server's CAS compares raw bytes: it base64-decodes this value
        and checks equality against the current file content.
        """
        path = self._ref_path(ref_id)
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            content = f.read()
        return base64.b64encode(content).decode('ascii')

    # --- internal ---

    def _head_path(self) -> str:
        return os.path.join(self.vault_path, REFS_DIR, HEAD_FILE)

    def _ref_path(self, ref_id: str) -> str:
        return os.path.join(self.vault_path, BARE_REFS_DIR, ref_id)
