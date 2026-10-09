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

    def resolve_tls_verify(self, verify_flag, directory: str) -> bool:
        # CLI flag takes precedence (True/False); None means "fall back to
        # remote config, default True". This mirrors --base-url / --token.
        if verify_flag is False:
            return False
        if verify_flag is True:
            return True
        if not directory:
            return True
        try:
            from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
            default = Vault__Remote_Manager().get_default(directory)
            if default is not None:
                return bool(default.tls_verify)
        except Exception:
            pass
        return True

    def resolve_remote(self, args, directory: str) -> dict:
        """Resolve the active remote for a network command.

        Returns a dict with keys:
            name        : str  ('' if no named remote, '<flag>' if --base-url override)
            base_url    : str
            tls_verify  : bool

        Precedence:
            1. --base-url  (explicit URL override; tls_verify still from CLI flag or default True)
            2. --remote NAME  (load that remote's URL + tls_verify from config)
            3. Default remote in config (URL + tls_verify)
            4. Legacy fallback: .sg_vault/local/base_url file (tls_verify defaults True)
        """
        base_url_flag = getattr(args, 'base_url',   None)
        remote_flag   = getattr(args, 'remote',     None)
        verify_flag   = getattr(args, 'verify_tls', None)

        if base_url_flag:
            return {'name'       : '--base-url',
                    'base_url'   : self.resolve_base_url(base_url_flag, directory),
                    'tls_verify' : self.resolve_tls_verify(verify_flag, directory)}

        if remote_flag and directory:
            try:
                from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
                remote = Vault__Remote_Manager().get_remote(directory, remote_flag)
                if remote is None:
                    raise RuntimeError(f'Remote {remote_flag!r} not found. '
                                       f'Run "sgit remote list" to see configured remotes.')
                tls = bool(remote.tls_verify) if verify_flag is None else bool(verify_flag)
                return {'name'       : str(remote.name),
                        'base_url'   : str(remote.url),
                        'tls_verify' : tls}
            except RuntimeError:
                raise
            except Exception:
                pass

        if directory:
            try:
                from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
                default = Vault__Remote_Manager().get_default(directory)
                if default is not None:
                    tls = bool(default.tls_verify) if verify_flag is None else bool(verify_flag)
                    return {'name'       : str(default.name),
                            'base_url'   : str(default.url),
                            'tls_verify' : tls}
            except Exception:
                pass

        base_url = self.resolve_base_url(None, directory)
        if not base_url and directory and os.path.isdir(os.path.join(directory, '.sg_vault')):
            base_url = self._unrecorded_server()
        return {'name'       : '',
                'base_url'   : base_url,
                'tls_verify' : self.resolve_tls_verify(verify_flag, directory)}

    def _unrecorded_server(self) -> str:
        """A vault made before init recorded its server. The default applies, and when
        SGIT_DEFAULT_BASE_URL changes it, say so: one exported variable in a CI job or
        a devcontainer otherwise sent the token, the write key and the data to whatever
        host it named, silently (review S1). Never recorded, so unsetting it undoes it."""
        import sys
        from sgit_ai.network.api.Vault__API import Vault__API, DEFAULT_BASE_URL
        server = Vault__API().default_base_url()
        if server != DEFAULT_BASE_URL:
            print(f'warning: this vault records no server; using SGIT_DEFAULT_BASE_URL={server}. '
                  f'Record one with `sgit remote add origin <url>` (or pass --base-url).', file=sys.stderr)
        return server

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
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        Vault__Storage().write_private(token_path, token)

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
        """The read key for the local history / inspect commands, or None.

        --vault-key takes whatever clone takes: a vault key, a read key declared by its
        prefix, or the bare {64-hex}:{vault_id} read-key shorthand (clone's rule). Without
        it: the vault key of a full clone, else the read key a read-only clone holds in
        clone_mode.json (which has no vault key file: history used to come back empty).
        Raises ValueError for a declared read key that does not parse."""
        raw = getattr(args, 'vault_key', None)
        if raw:
            return self.read_key_from_credential(raw)
        directory = getattr(args, 'directory', '.') or '.'
        vault_key = self.load_vault_key(directory)
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto, READ_KEY_PREFIX
        if vault_key:                                   # a vault key by definition: never the shorthand
            return Vault__Crypto().derive_keys_from_vault_key(vault_key)['read_key_bytes']
        clone_mode = self.load_clone_mode(directory)
        if clone_mode.get('mode') == 'read-only' and clone_mode.get('read_key'):
            return self.read_key_from_credential(READ_KEY_PREFIX + Vault__Crypto().strip_key_prefix(str(clone_mode['read_key'])))
        return None

    def read_key_from_credential(self, raw: str) -> bytes:
        import re
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.safe_types.Enum__Key_Kind import Enum__Key_Kind
        crypto = Vault__Crypto()
        raw    = (raw or '').strip()
        kind   = crypto.classify_key(raw)
        body   = crypto.strip_key_prefix(raw)
        head   = body.partition(':')[0]
        if kind == Enum__Key_Kind.VAULT:
            return crypto.derive_keys_from_vault_key(body)['read_key_bytes']
        is_read_shape = bool(re.fullmatch(r'[0-9a-fA-F]{64}', head))
        if kind in (Enum__Key_Kind.READ_PRIVATE, Enum__Key_Kind.READ_PUBLIC) or is_read_shape:
            if not is_read_shape:
                raise ValueError('this declares a read key, but it does not start with 64 hex characters')
            return bytes.fromhex(head)
        return crypto.derive_keys_from_vault_key(body)['read_key_bytes']
