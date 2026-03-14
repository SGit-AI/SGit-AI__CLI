import os
from osbot_utils.type_safe.Type_Safe import Type_Safe


TOKEN_FILE = 'token'


class CLI__Token_Store(Type_Safe):

    def resolve_token(self, token: str, directory: str) -> str:
        if token:
            self.save_token(token, directory)
            return token
        return self.load_token(directory)

    def save_token(self, token: str, directory: str):
        sg_vault_dir = os.path.join(directory, '.sg_vault')
        if os.path.isdir(sg_vault_dir):
            token_path = os.path.join(sg_vault_dir, TOKEN_FILE)
            with open(token_path, 'w') as f:
                f.write(token)

    def load_token(self, directory: str) -> str:
        token_path = os.path.join(directory, '.sg_vault', TOKEN_FILE)
        if os.path.isfile(token_path):
            with open(token_path, 'r') as f:
                return f.read().strip()
        return ''

    def load_vault_key(self, directory: str) -> str:
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
