import getpass
import sys
import time
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sg_send_cli.crypto.Vault__Crypto            import Vault__Crypto
from sg_send_cli.api.Vault__API                  import Vault__API
from sg_send_cli.sync.Vault__Sync                import Vault__Sync
from sg_send_cli.sync.Vault__Bare                import Vault__Bare
from sg_send_cli.objects.Vault__Inspector         import Vault__Inspector
from sg_send_cli.cli.CLI__Token_Store            import CLI__Token_Store
from sg_send_cli.cli.CLI__Credential_Store       import CLI__Credential_Store


class CLI__Vault(Type_Safe):
    token_store      : CLI__Token_Store
    credential_store : CLI__Credential_Store

    def create_sync(self, base_url: str = None, access_token: str = None) -> Vault__Sync:
        api = Vault__API(base_url=base_url or '', access_token=access_token or '')
        api.setup()
        return Vault__Sync(crypto=Vault__Crypto(), api=api)

    def cmd_init(self, args):
        if not args.token:
            print('Error: --token is required for init (needed to write to the remote vault).', file=sys.stderr)
            sys.exit(1)
        sync      = self.create_sync(args.base_url, args.token)
        vault_key = getattr(args, 'vault_key', None) or None
        result    = sync.init(args.directory, vault_key=vault_key)
        self.token_store.save_token(args.token, result['directory'])
        print(f'Initialized empty vault in {result["directory"]}/')
        print(f'  Vault ID:  {result["vault_id"]}')
        print(f'  Vault key: {result["vault_key"]}')
        print(f'  Branch:    {result["branch_id"]}')
        print()
        print('Save your vault key — you need it to clone this vault on another machine.')

    def cmd_commit(self, args):
        sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        message = getattr(args, 'message', '') or ''
        result  = sync.commit(args.directory, message=message)
        print(f'[{result["branch_id"][:20]}] {result["message"]}')
        print(f'  commit {result["commit_id"]}')

    def cmd_status(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.status(args.directory)
        if result['clean']:
            print('Vault is clean — no uncommitted changes.')
        else:
            for f in result['added']:
                print(f'  + {f}')
            for f in result['modified']:
                print(f'  ~ {f}')
            for f in result['deleted']:
                print(f'  - {f}')

    def cmd_pull(self, args):
        token  = self.token_store.resolve_token(args.token, args.directory)
        sync   = self.create_sync(args.base_url, token)
        result = sync.pull(args.directory)

        status = result.get('status', '')
        if status == 'up_to_date':
            print('Already up to date.')
        elif status == 'conflicts':
            conflicts = result.get('conflicts', [])
            print(f'CONFLICT: {len(conflicts)} file(s) have merge conflicts.')
            for c in conflicts:
                print(f'  ! {c}')
            print()
            print('Fix the conflicts and then run:')
            print('  sg-send-cli commit')
            print()
            print('Or abort the merge with:')
            print('  sg-send-cli merge-abort')
        else:
            added    = len(result.get('added', []))
            modified = len(result.get('modified', []))
            deleted  = len(result.get('deleted', []))
            for f in result.get('added', []):
                print(f'  + {f}')
            for f in result.get('modified', []):
                print(f'  ~ {f}')
            for f in result.get('deleted', []):
                print(f'  - {f}')
            if added + modified + deleted == 0:
                print('Merged (no file changes).')
            else:
                print(f'Merged: {added} added, {modified} modified, {deleted} deleted')

    def cmd_push(self, args):
        token  = self.token_store.resolve_token(args.token, args.directory)
        sync   = self.create_sync(args.base_url, token)
        result = sync.push(args.directory)

        status = result.get('status', '')
        if status == 'up_to_date':
            print('Nothing to push — vault is up to date.')
        else:
            uploaded = result.get('objects_uploaded', 0)
            commits  = result.get('commits_pushed', 0)
            print(f'Pushed {commits} commit(s), {uploaded} object(s) uploaded.')
            print(f'  commit {result.get("commit_id", "")}')

    def cmd_branches(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.branches(args.directory)

        branches = result.get('branches', [])
        if not branches:
            print('No branches found.')
            return

        for b in branches:
            marker = '* ' if b['is_current'] else '  '
            name   = b['name']
            btype  = b['branch_type']
            head   = b['head_commit'][:12] if b['head_commit'] else '(none)'
            print(f'{marker}{name} ({btype}) -> {head}')

    def cmd_merge_abort(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.merge_abort(args.directory)
        print(f'Merge aborted. Restored to commit {result["restored_commit"]}.')
        removed = result.get('removed_files', [])
        if removed:
            for f in removed:
                print(f'  removed {f}')

    # --- Bare vault commands ---

    def cmd_checkout(self, args):
        vault_key = getattr(args, 'vault_key', None)
        if not vault_key:
            vault_key = self.token_store.load_vault_key(args.directory)
        if not vault_key:
            print('Error: --vault-key is required for bare vaults (no VAULT-KEY on disk).', file=sys.stderr)
            sys.exit(1)
        bare = Vault__Bare(crypto=Vault__Crypto())
        bare.checkout(args.directory, vault_key)
        files = bare.list_files(args.directory, vault_key)
        print(f'Checked out {len(files)} files to {args.directory}/')

    def cmd_clean(self, args):
        bare = Vault__Bare(crypto=Vault__Crypto())
        bare.clean(args.directory)
        print(f'Cleaned working copy from {args.directory}/ (bare vault remains)')

    # --- Credential store commands ---

    def setup_credential_store(self, sg_send_dir: str = None):
        self.credential_store.setup(sg_send_dir)

    def cmd_vault_add(self, args):
        passphrase = self.credential_store._prompt_passphrase(confirm=True)
        vault_key  = getattr(args, 'vault_key', None) or getpass.getpass('Vault key: ')
        self.credential_store.add_vault(passphrase, args.alias, vault_key)
        print(f'Saved \'{args.alias}\' to credential store')

    def cmd_vault_list(self, args):
        passphrase = self.credential_store._prompt_passphrase()
        aliases    = self.credential_store.list_vaults(passphrase)
        if not aliases:
            print('No stored vaults.')
        else:
            for alias in aliases:
                print(f'  {alias}')

    def cmd_vault_remove(self, args):
        passphrase = self.credential_store._prompt_passphrase()
        removed    = self.credential_store.remove_vault(passphrase, args.alias)
        if removed:
            print(f'Removed \'{args.alias}\'')
        else:
            print(f'No vault found for \'{args.alias}\'')

    def cmd_vault_show(self, args):
        passphrase = self.credential_store._prompt_passphrase()
        vault_key  = self.credential_store.get_vault_key(passphrase, args.alias)
        if vault_key:
            print(vault_key)
        else:
            print(f'No vault found for \'{args.alias}\'')

    # --- Key derivation and inspection ---

    def cmd_derive_keys(self, args):
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(args.vault_key)
        print(f'vault_id:         {keys["vault_id"]}')
        print(f'read_key:         {keys["read_key"]}')
        print(f'write_key:        {keys["write_key"]}')
        print(f'tree_file_id:     {keys["tree_file_id"]}')
        print(f'settings_file_id: {keys["settings_file_id"]}')
        print(f'ref_file_id:      {keys["ref_file_id"]}')

    def cmd_inspect(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        print(inspector.format_vault_summary(args.directory))

    def cmd_inspect_object(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        print(inspector.format_object_detail(args.directory, args.object_id))

    def cmd_inspect_tree(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        read_key  = self.token_store.resolve_read_key(args)
        result    = inspector.inspect_tree(args.directory, read_key=read_key)
        if result.get('error'):
            print(f'Error: {result["error"]}')
            return
        if not result.get('entries'):
            print('(no tree entries)')
            return
        print(f'Tree from commit {result["commit_id"]} (tree {result["tree_id"]})')
        print(f'  {result["file_count"]} files, {result["total_size"]} bytes total')
        print()
        for entry in result['entries']:
            print(f'  {entry["blob_id"]}  {entry["size"]:>8}  {entry["path"]}')

    def cmd_inspect_log(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        read_key  = self.token_store.resolve_read_key(args)
        chain     = inspector.inspect_commit_chain(args.directory, read_key=read_key)
        oneline   = getattr(args, 'oneline', False)
        graph     = getattr(args, 'graph', False)
        print(inspector.format_commit_log(chain, oneline=oneline, graph=graph))

    def cmd_cat_object(self, args):
        crypto    = Vault__Crypto()
        inspector = Vault__Inspector(crypto=crypto)
        read_key  = self.token_store.resolve_read_key(args)
        if not read_key:
            print('Error: no vault key found. Provide --vault-key or run from a vault directory.', file=sys.stderr)
            sys.exit(1)
        print(inspector.format_cat_object(args.directory, args.object_id, read_key))

    def cmd_inspect_stats(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        stats     = inspector.object_store_stats(args.directory)
        print(f'=== Object Store Stats ===')
        print(f'  Total objects: {stats["total_objects"]}')
        print(f'  Total size:    {stats["total_bytes"]} bytes')
        if stats['buckets']:
            print(f'  Buckets:')
            for prefix, count in sorted(stats['buckets'].items()):
                print(f'    {prefix}/ : {count} objects')

    def cmd_log(self, args):
        self.cmd_inspect_log(args)
