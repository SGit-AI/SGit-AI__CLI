import os
from osbot_utils.type_safe.Type_Safe import Type_Safe


TOKEN_FILE    = 'token'
BASE_URL_FILE = 'base_url'


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

    def save_token(self, token: str, directory: str):
        if not directory:
            return
        sg_vault_dir = os.path.join(directory, '.sg_vault')
        if os.path.isdir(sg_vault_dir):
            token_path = os.path.join(sg_vault_dir, TOKEN_FILE)
            with open(token_path, 'w') as f:
                f.write(token)

    def load_token(self, directory: str) -> str:
        if not directory:
            return ''
        token_path = os.path.join(directory, '.sg_vault', TOKEN_FILE)
        if os.path.isfile(token_path):
            with open(token_path, 'r') as f:
                return f.read().strip()
        return ''

    def save_base_url(self, base_url: str, directory: str):
        if not directory or not base_url:
            return
        sg_vault_dir = os.path.join(directory, '.sg_vault')
        if os.path.isdir(sg_vault_dir):
            url_path = os.path.join(sg_vault_dir, BASE_URL_FILE)
            with open(url_path, 'w') as f:
                f.write(base_url)

    def load_base_url(self, directory: str) -> str:
        if not directory:
            return ''
        url_path = os.path.join(directory, '.sg_vault', BASE_URL_FILE)
        if os.path.isfile(url_path):
            with open(url_path, 'r') as f:
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

    def resolve_read_key(self, args) -> bytes:
        vault_key = getattr(args, 'vault_key', None)
        if not vault_key:
            directory = getattr(args, 'directory', '.')
            vault_key = self.load_vault_key(directory)
        if not vault_key:
            return None
        from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(vault_key)
        return keys['read_key_bytes']
