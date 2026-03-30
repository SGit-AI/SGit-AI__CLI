import json
import os
import sys
from datetime import datetime, timezone
from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.api.API__Transfer               import API__Transfer, DEFAULT_BASE_URL
from sgit_ai.cli.CLI__Input                  import CLI__Input
from sgit_ai.cli.CLI__Token_Store            import CLI__Token_Store
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.sync.Vault__Storage             import Vault__Storage
from sgit_ai.transfer.Vault__Transfer        import Vault__Transfer

SHARE_HISTORY_FILE = 'share_history.json'


class CLI__Share(Type_Safe):
    token_store : CLI__Token_Store
    debug_log   : object = None

    def _history_path(self, directory: str) -> str:
        return os.path.join(directory, '.sg_vault', 'local', SHARE_HISTORY_FILE)

    def _append_share_history(self, directory: str, entry: dict):
        """Append one share entry to .sg_vault/local/share_history.json."""
        path    = self._history_path(directory)
        history = []
        if os.path.isfile(path):
            try:
                with open(path, 'r') as f:
                    history = json.load(f)
            except Exception:
                history = []
        history.append(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(history, f, indent=2)

    def cmd_share(self, args):
        directory    = getattr(args, 'directory', '.')
        base_url     = getattr(args, 'base_url',  None) or DEFAULT_BASE_URL
        access_token = self.token_store.load_token(directory)
        if not access_token:
            token_raw = CLI__Input().prompt('Access token: ')
            if token_raw is None or not token_raw.strip():
                print('error: an access token is required to share.', file=sys.stderr)
                sys.exit(1)
            access_token = token_raw.strip()
            self.token_store.save_token(access_token, directory)

        api      = API__Transfer(base_url=base_url, access_token=access_token,
                                 debug_log=self.debug_log)
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())
        transfer.setup()

        try:
            result = transfer.share(directory)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        token           = result['token']
        transfer_id     = result['transfer_id']
        derived_xfer_id = result['derived_xfer_id']
        commit_id       = result['commit_id']
        aes_key_hex     = result['aes_key_hex']
        folder_hash     = result['folder_hash']
        file_count      = result['file_count']
        total_kb        = result['total_bytes'] / 1024

        # Record this share in local history
        self._append_share_history(directory, dict(
            timestamp   = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            commit_id   = commit_id,
            token       = token,
            transfer_id = transfer_id,
            folder_hash = folder_hash,
            file_count  = file_count,
            total_bytes = result['total_bytes'],
        ))

        print(f'  Token:          {token}')
        print(f'  Transfer ID:    {transfer_id}')
        print(f'  Derived XID:    {derived_xfer_id}', end='')
        print('' if transfer_id == derived_xfer_id else '  *** MISMATCH — server ignored requested ID ***')
        print(f'  Commit:         {commit_id}')
        print(f'  Folder hash:    {folder_hash}')
        print(f'  AES key (hex):  {aes_key_hex}')
        print(f'  Files:          {file_count} file(s), {total_kb:.1f} KB')
        print(f'  History:        .sg_vault/local/{SHARE_HISTORY_FILE}')
        print()
        print('Upload complete. Share this token:')
        print()
        print(f'  {token}')
        print()
        print('Anyone with this token can download and decrypt the vault snapshot at:')
        print(f'  https://send.sgraph.ai/en-gb/browse/#{token}')
        print()
        print('Next:')
        print('  sgit share   — share again with a new token')
        print('  sgit status  — check vault state')

        browse_url = f'https://send.sgraph.ai/en-gb/browse/#{token}'
        answer = CLI__Input().prompt('\nOpen in browser? [Y/n] ')
        if answer is not None and answer.strip().lower() in ('', 'y', 'yes'):
            import webbrowser
            webbrowser.open(browse_url)
