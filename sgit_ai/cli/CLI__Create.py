"""CLI__Create — one-shot `sgit create`: init + push in a single command."""
import sys

from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sgit_ai.api.Vault__API             import Vault__API
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.core.Vault__Sync           import Vault__Sync


class CLI__Create(Type_Safe):
    """Implements `sgit create <vault-name>` — init + push in one step."""

    vault_ref  : object = None  # CLI__Vault instance injected by CLI__Main
    token_store: object = None  # CLI__Token_Store injected by CLI__Main

    def cmd_create(self, args):
        """sgit create <vault-name>

        Creates a new vault, commits the initial state, and pushes it to the
        remote server — equivalent to:  sgit init <dir> && sgit commit && sgit push
        """
        import os as _os
        from sgit_ai.transfer.Simple_Token          import Simple_Token
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist

        vault_name  = getattr(args, 'vault_name', None)
        directory   = getattr(args, 'directory', None) or vault_name or '.'
        vault_key   = getattr(args, 'vault_key',  None)
        token       = getattr(args, 'token',      None)
        base_url    = getattr(args, 'base_url',   None)
        push        = not getattr(args, 'no_push', False)

        if not vault_name:
            print('error: vault name is required', file=sys.stderr)
            sys.exit(1)

        # Resolve access token if vault_ref available
        if self.vault_ref and not token:
            token   = self.vault_ref.token_store.resolve_token(None, None)
            base_url = self.vault_ref.token_store.resolve_base_url(base_url, None)

        # Build sync with network API
        api  = Vault__API(base_url=base_url or '', access_token=token or '')
        api.setup()
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)

        # ---- Step 1: init ----
        print(f"Initialising vault '{vault_name}'...")
        init_token = None
        if vault_key and Simple_Token.is_simple_token(vault_key):
            init_token = vault_key
            vault_key  = None
        elif not vault_key:
            if Simple_Token.is_simple_token(vault_name):
                init_token = vault_name
            # Otherwise let sync.init() auto-generate

        result = sync.init(directory, vault_key=vault_key, allow_nonempty=True,
                           token=init_token)
        vault_id  = result['vault_id']
        vault_dir = result['directory']

        print(f'  Vault ID:  {vault_id}')
        print(f'  Directory: {vault_dir}/')

        # Save token/base_url against new directory
        if token and self.vault_ref:
            self.vault_ref.token_store.save_token(token, vault_dir)
        if base_url and self.vault_ref:
            self.vault_ref.token_store.save_base_url(base_url, vault_dir)

        # ---- Step 2: commit if there are files ----
        has_files = any(
            True for root, dirs, files in _os.walk(vault_dir)
            if any(f for f in files) and '.sg_vault' not in root
        )
        if has_files:
            print('  Committing existing files...')
            commit_result = sync.commit(vault_dir, message='Initial commit (sgit create)')
            n_files = commit_result.get('files_changed', 0)
            print(f'  Committed {n_files} file(s).')

        # ---- Step 3: push ----
        if push:
            if not token:
                print('  No access token — skipping push. Run `sgit push` to upload.', file=sys.stderr)
            else:
                print('  Pushing to remote...')
                try:
                    push_result = sync.push(vault_dir)
                    uploaded    = push_result.get('objects_uploaded', 0)
                    commits     = push_result.get('commits_pushed',   0)
                    print(f'  Pushed {commits} commit(s), {uploaded} object(s) uploaded.')
                except Exception as exc:
                    print(f'  Push failed: {exc}', file=sys.stderr)
                    print('  Vault initialised locally — run `sgit push` when ready.', file=sys.stderr)

        # ---- Derive read key ----
        read_key = None
        try:
            full_key = result.get('vault_key') or vault_key
            if full_key:
                keys     = Vault__Crypto().derive_keys_from_vault_key(full_key)
                read_key = keys.get('read_key')
        except Exception:
            pass

        print()
        print('Vault ready.')
        if result.get('vault_key'):
            print(f'  Vault key: {result["vault_key"]}')
            print('  (Save your vault key — it is the only way to access your vault elsewhere.)')
        if read_key:
            print(f'  Read key:  {read_key}  (share for read-only access)')
        print()
        print('Next steps:')
        print(f'  cd {vault_dir}')
        print( '  sgit status          — check vault state')
        print( '  sgit share           — share a snapshot via a simple token')
