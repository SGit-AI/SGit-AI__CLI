import os
import stat
from osbot_utils.type_safe.Type_Safe import Type_Safe


TOKEN_FILE    = 'token'
BASE_URL_FILE = 'base_url'

LOCAL_DIR     = os.path.join('.sg_vault', 'local')


class CLI__Token_Store(Type_Safe):

    def resolve_token(self, token: str, directory: str) -> str:
        if token:
            if directory:
                self.save_token(token, directory)
            return token
        if not directory:
            return ''
        return self.load_token(directory)

    def resolve_base_url(self, base_url: str, directory: str) -> str:
        if base_url:
            if directory:
                self.save_base_url(base_url, directory)
            return base_url
        if not directory:
            return ''
        return self.load_base_url(directory)

    def _local_dir(self, directory: str) -> str:
        return os.path.join(directory, '.sg_vault', 'local')

    def save_token(self, token: str, directory: str):
        if not directory:
            return
        sg_vault_dir = os.path.join(directory, '.sg_vault')
        if not os.path.isdir(sg_vault_dir):
            return
        local_dir  = self._local_dir(directory)
        os.makedirs(local_dir, exist_ok=True)
        token_path = os.path.join(local_dir, TOKEN_FILE)
        with open(token_path, 'w') as f:
            f.write(token)
        try:
            os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def load_token(self, directory: str) -> str:
        if not directory:
            return ''
        # Primary: local/ subdirectory
        token_path = os.path.join(self._local_dir(directory), TOKEN_FILE)
        if os.path.isfile(token_path):
            with open(token_path, 'r') as f:
                return f.read().strip()
        # Fallback: legacy location directly under .sg_vault/
        legacy_path = os.path.join(directory, '.sg_vault', TOKEN_FILE)
        if os.path.isfile(legacy_path):
            with open(legacy_path, 'r') as f:
                return f.read().strip()
        return ''

    def save_base_url(self, base_url: str, directory: str):
        if not directory or not base_url:
            return
        sg_vault_dir = os.path.join(directory, '.sg_vault')
        if not os.path.isdir(sg_vault_dir):
            return
        local_dir    = self._local_dir(directory)
        os.makedirs(local_dir, exist_ok=True)
        base_url_path = os.path.join(local_dir, BASE_URL_FILE)
        with open(base_url_path, 'w') as f:
            f.write(base_url)
        try:
            os.chmod(base_url_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def load_base_url(self, directory: str) -> str:
        if not directory:
            return ''
        # Primary: local/ subdirectory
        url_path = os.path.join(self._local_dir(directory), BASE_URL_FILE)
        if os.path.isfile(url_path):
            with open(url_path, 'r') as f:
                return f.read().strip()
        # Fallback: legacy location directly under .sg_vault/
        legacy_path = os.path.join(directory, '.sg_vault', BASE_URL_FILE)
        if os.path.isfile(legacy_path):
            with open(legacy_path, 'r') as f:
                return f.read().strip()
        return ''

    def load_vault_key(self, directory: str) -> str:
        if not directory:
            return ''
        vault_key_path = os.path.join(directory, '.sg_vault', 'local', 'vault_key')
        if not os.path.isfile(vault_key_path):
            vault_key_path = os.path.join(directory, '.sg_vault', 'VAULT-KEY')
        if os.path.isfile(vault_key_path):
            with open(vault_key_path, 'r') as f:
                return f.read().strip()
        return ''

    def load_clone_mode(self, directory: str) -> dict:
        import json
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        path = Vault__Storage().clone_mode_path(directory)
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {'mode': 'full'}

    def resolve_read_key(self, args) -> bytes:
        vault_key = getattr(args, 'vault_key', None)
        if not vault_key:
            directory = getattr(args, 'directory', '.')
            vault_key = self.load_vault_key(directory)
        if not vault_key:
            return None
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(vault_key)
        return keys['read_key_bytes']
