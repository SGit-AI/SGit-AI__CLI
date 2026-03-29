import json
import os
import sys
from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.api.API__Transfer               import API__Transfer, DEFAULT_BASE_URL
from sgit_ai.cli.CLI__Token_Store            import CLI__Token_Store
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.sync.Vault__Storage             import Vault__Storage
from sgit_ai.transfer.Vault__Transfer        import Vault__Transfer


class CLI__Share(Type_Safe):
    token_store : CLI__Token_Store
    debug_log   : object = None

    def _load_share_config(self, directory: str) -> dict:
        """Read share_token / share_transfer_id from local/config.json."""
        config_path = Vault__Storage().local_config_path(directory)
        if not os.path.isfile(config_path):
            return {}
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_share_config(self, directory: str, token: str, transfer_id: str):
        """Persist share_token and share_transfer_id into local/config.json."""
        config_path = Vault__Storage().local_config_path(directory)
        config      = {}
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
            except Exception:
                pass
        config['share_token']       = token
        config['share_transfer_id'] = transfer_id
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def cmd_share(self, args):
        directory  = getattr(args, 'directory', '.')
        token_str  = getattr(args, 'token',    None)
        rotate     = getattr(args, 'rotate',   False)
        base_url   = getattr(args, 'base_url', None)

        base_url     = base_url or self.token_store.load_base_url(directory) or DEFAULT_BASE_URL
        access_token = self.token_store.load_token(directory)
        if not access_token and sys.stdin.isatty():
            access_token = input('Access token: ').strip()
            if not access_token:
                print('error: an access token is required to share.', file=sys.stderr)
                sys.exit(1)
            self.token_store.save_token(access_token, directory)

        # Reuse existing share_token unless --rotate or an explicit --token was given
        if not token_str and not rotate:
            config    = self._load_share_config(directory)
            token_str = config.get('share_token')
            if token_str:
                print(f'Reusing share token: {token_str}')
            else:
                print('Generating share token...')
        else:
            print('Generating share token...')

        api      = API__Transfer(base_url=base_url, access_token=access_token,
                                 debug_log=self.debug_log)
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())
        transfer.setup()

        try:
            result = transfer.share(directory, token_str=token_str)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        token           = result['token']
        transfer_id     = result['transfer_id']
        derived_xfer_id = result['derived_xfer_id']
        aes_key_hex     = result['aes_key_hex']
        folder_hash     = result['folder_hash']
        file_count      = result['file_count']
        total_kb        = result['total_bytes'] / 1024

        # Persist for next run
        self._save_share_config(directory, token, transfer_id)

        print(f'  Token:          {token}')
        print(f'  Transfer ID:    {transfer_id}')
        print(f'  Derived XID:    {derived_xfer_id}', end='')
        print('' if transfer_id == derived_xfer_id else '  *** MISMATCH — server ignored requested ID ***')
        print(f'  Folder hash:    {folder_hash}')
        print(f'  AES key (hex):  {aes_key_hex}')
        print(f'  Files:          {file_count} file(s), {total_kb:.1f} KB')
        print()
        print('Upload complete. Share this token:')
        print()
        print(f'  {token}')
        print()
        print('Anyone with this token can download and decrypt the vault snapshot at:')
        print(f'  https://send.sgraph.ai/en-gb/browse/#{token}')
        print()
        print('Next:')
        print('  sgit share           — re-share (same token, updated content)')
        print('  sgit share --rotate  — rotate to a new token')
        print('  sgit status          — check vault state')

        browse_url = f'https://send.sgraph.ai/en-gb/browse/#{token}'
        if sys.stdin.isatty():
            try:
                answer = input(f'\nOpen in browser? [Y/n] ').strip().lower()
            except EOFError:
                answer = 'n'
            if answer in ('', 'y', 'yes'):
                import webbrowser
                webbrowser.open(browse_url)
