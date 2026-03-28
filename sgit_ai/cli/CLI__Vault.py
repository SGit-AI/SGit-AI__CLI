import getpass
import sys
import time
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.api.Vault__API                  import Vault__API
from sgit_ai.sync.Vault__Sync                import Vault__Sync
from sgit_ai.sync.Vault__Bare                import Vault__Bare
from sgit_ai.objects.Vault__Inspector         import Vault__Inspector
from sgit_ai.cli.CLI__Token_Store            import CLI__Token_Store
from sgit_ai.cli.CLI__Credential_Store       import CLI__Credential_Store
from sgit_ai.cli.CLI__Progress               import CLI__Progress


class CLI__Vault(Type_Safe):
    token_store      : CLI__Token_Store
    credential_store : CLI__Credential_Store
    debug_log        : object = None

    def create_sync(self, base_url: str = None, access_token: str = None) -> Vault__Sync:
        api = Vault__API(base_url=base_url or '', access_token=access_token or '',
                         debug_log=self.debug_log)
        api.setup()
        return Vault__Sync(crypto=Vault__Crypto(), api=api)

    def cmd_clone(self, args):
        token     = self.token_store.resolve_token(getattr(args, 'token', None), None)
        base_url  = getattr(args, 'base_url', None)
        sync      = self.create_sync(base_url, token)
        vault_key = args.vault_key
        directory = args.directory
        if not directory:
            parts    = vault_key.split(':')
            vault_id = parts[-1] if len(parts) == 2 else 'vault'
            directory = vault_id
        progress = CLI__Progress()
        print(f'Cloning into \'{directory}\'...')
        result   = sync.clone(vault_key, directory, on_progress=progress.callback)
        if token:
            self.token_store.save_token(token, result['directory'])
        if base_url:
            self.token_store.save_base_url(base_url, result['directory'])
        print()
        print(f'Cloned into {result["directory"]}/')
        print(f'  Vault ID:  {result["vault_id"]}')
        print(f'  Branch:    {result["branch_id"]}')
        if result.get('commit_id'):
            print(f'  HEAD:      {result["commit_id"]}')

    def cmd_init(self, args):
        import glob as _glob
        sync       = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        vault_key  = getattr(args, 'vault_key', None) or None
        directory  = args.directory
        restore    = getattr(args, 'restore', False)
        existing   = getattr(args, 'existing', False)

        # --restore mode: look for a .vault__*.zip in the target directory
        if restore:
            import os as _os
            import re as _re
            search_dir = _os.path.abspath(directory) if directory else _os.getcwd()
            pattern    = _os.path.join(search_dir, '.vault__*.zip')
            backups    = sorted(_glob.glob(pattern))
            if not backups:
                print(f'error: no vault backup (.vault__*.zip) found in {search_dir}', file=sys.stderr)
                sys.exit(1)
            zip_path = backups[-1]  # use the most recent
            zip_name = _os.path.basename(zip_path)
            print(f'Found vault backup: {zip_name}')
            answer = input('Restore vault from this backup? [Y/n]: ').strip().lower()
            if answer in ('n', 'no'):
                print('Restore cancelled.')
                return
            result = sync.restore_from_backup(zip_path, search_dir)
            print()
            print('Vault restored from backup.')
            print(f'  Vault ID:  {result["vault_id"]}')
            print(f'  Branch:    {result["branch_id"]}')
            return

        # Check for non-empty directory
        import os as _os
        if not existing and _os.path.exists(directory):
            sg_vault = _os.path.join(directory, '.sg_vault')
            entries  = [e for e in _os.listdir(directory) if e != '.sg_vault']
            if entries:
                n = len(entries)
                answer = input(f"Directory '{directory}' is not empty ({n} file(s) found).\n"
                               f'Initialise vault here anyway? [y/N]: ').strip().lower()
                if answer not in ('y', 'yes'):
                    print('Init cancelled.')
                    return
                existing = True

        result = sync.init(directory, vault_key=vault_key, allow_nonempty=existing)
        token  = getattr(args, 'token', None)
        if token:
            self.token_store.save_token(token, result['directory'])
        print(f'Vault created!  Vault ID: {result["vault_id"]}')
        print(f'  Directory: {result["directory"]}/')
        print(f'  Vault key: {result["vault_key"]}')
        print(f'  Branch:    {result["branch_id"]}')
        print()
        print('  Save your vault key — it is the only way to access your vault on another machine.')
        print()
        print('Next steps:')
        print('  sgit commit           — commit your files to the vault')
        print('  sgit push             — upload the vault to the server')
        print('  sgit share            — share a snapshot via a simple token')

        # Offer to commit existing files if the directory was non-empty
        if existing:
            import os as _os
            has_files = any(
                True for root, dirs, files in _os.walk(directory)
                if any(f for f in files) and '.sg_vault' not in root
            )
            if has_files:
                print()
                answer = input('Commit all existing files now? [Y/n]: ').strip().lower()
                if answer not in ('n', 'no'):
                    commit_result = sync.commit(directory, message='Initial commit')
                    print(f'Committed {commit_result.get("files_changed", 0)} file(s).')

    def cmd_uninit(self, args):
        import os as _os
        directory = getattr(args, 'directory', '.') or '.'
        sync      = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())

        print('Creating vault backup...')
        result = sync.uninit(directory)

        backup_path  = result['backup_path']
        backup_size  = result['backup_size']
        working_files = result['working_files']
        backup_name   = _os.path.basename(backup_path)
        size_mb       = backup_size / (1024 * 1024)

        print(f'  Backup: {backup_name} ({size_mb:.1f} MB)')
        print()
        abs_dir = _os.path.abspath(directory)
        folder  = _os.path.basename(abs_dir)
        print(f'Removing .sg_vault/ from {folder}/...')
        print(f'  Working files: untouched ({working_files} files)')
        print()
        print(f'Vault removed. Backup saved: {backup_name}')
        print()
        print('To restore later:')
        print('  sgit init --restore .')

    def cmd_commit(self, args):
        sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        message = getattr(args, 'message', '') or ''
        result  = sync.commit(args.directory, message=message)
        files_changed = result.get('files_changed', 0)
        branch_short  = result['branch_id'][:20]
        print(f'Committed {files_changed} file(s) to {branch_short}.')
        print(f'  Commit: {result["commit_id"]}')
        print()
        print('Next:')
        print('  sgit push             — upload this commit to the server')
        print('  sgit diff             — review what changed')
        print('  sgit status           — check vault state')

    def cmd_status(self, args):
        sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result  = sync.status(args.directory)
        explain = getattr(args, 'explain', False)

        clone_branch_id   = result.get('clone_branch_id', '')
        named_branch_id   = result.get('named_branch_id', '')
        push_status       = result.get('push_status', 'unknown')
        ahead             = result.get('ahead', 0)
        behind            = result.get('behind', 0)
        remote_configured = result.get('remote_configured', False)
        never_pushed      = result.get('never_pushed', False)

        if clone_branch_id:
            print(f'On branch: {clone_branch_id}  →  {named_branch_id}')
            if not remote_configured:
                print('  Remote: not configured — run: sgit remote add origin <url> <vault-id>')
                print('          (vault exists only locally until pushed)')
            elif push_status == 'up_to_date':
                print('  Remote: in sync with remote')
            elif push_status == 'ahead':
                commit_word = 'commit' if ahead == 1 else 'commits'
                print(f'  Remote: your branch is {ahead} {commit_word} ahead of remote — run: sgit push')
            elif push_status == 'behind':
                commit_word = 'commit' if behind == 1 else 'commits'
                print(f'  Remote: remote has {behind} new {commit_word} — run: sgit pull')
            elif push_status == 'diverged':
                print(f'  Remote: diverged: {ahead} ahead, {behind} behind — run: sgit pull first, then sgit push')
            else:
                print('  Remote: remote status unknown (no remote configured or vault not pushed yet)')
            print()

        if never_pushed and clone_branch_id:
            print('  This vault has never been pushed. It only exists on this machine.')
            print('    Run: sgit push    to upload it to the server')
            print('    Run: sgit export  to save it as a local archive')
            print()

        if result['clean']:
            if push_status == 'ahead' and remote_configured:
                commit_word = 'commit' if ahead == 1 else 'commits'
                print(f'Nothing to commit, but {ahead} {commit_word} waiting to be pushed.')
                print('  Run: sgit push')
            elif push_status == 'up_to_date' and remote_configured:
                print('Nothing to commit. Vault is fully in sync.')
            else:
                print('Nothing to commit, working tree clean.')
        else:
            for f in result['added']:
                print(f'  + {f}')
            for f in result['modified']:
                print(f'  ~ {f}')
            for f in result['deleted']:
                print(f'  - {f}')
            print()
            print('  Run: sgit commit  — to save these changes to the vault')

        if explain:
            print()
            print('Note: sgit uses a two-branch model (unlike git):')
            print('  Your "clone branch" is your personal working branch (branch-clone-xxx)')
            print('  The "named branch" is the shared/canonical branch (branch-named-yyy)')
            print('  You commit to your clone branch, then push to update the named branch')
            print('  There is no staging area — all tracked files are committed together')
            print('  "ahead" means your clone has commits the named branch does not have yet')
            print('  Run "sgit push" to publish your clone branch commits to the named branch')

    def cmd_pull(self, args):
        token    = self.token_store.resolve_token(args.token, args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        progress = CLI__Progress()
        remote_label = base_url or 'default'
        print(f'Pulling from {remote_label}...')
        result   = sync.pull(args.directory, on_progress=progress.callback)

        status = result.get('status', '')
        if status == 'up_to_date':
            if result.get('remote_unreachable'):
                print('Already up to date (warning: could not reach remote).')
            else:
                print('Already up to date.')
        elif status == 'conflicts':
            conflicts = result.get('conflicts', [])
            print(f'CONFLICT: {len(conflicts)} file(s) have merge conflicts.')
            for c in conflicts:
                print(f'  ! {c}')
            print()
            print('Fix the conflicts and then run:')
            print('  sgit commit')
            print()
            print('Or abort the merge with:')
            print('  sgit merge-abort')
        else:
            added    = len(result.get('added', []))
            modified = len(result.get('modified', []))
            deleted  = len(result.get('deleted', []))
            print()
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
            print()
            print('Next:')
            print('  sgit push             — push your own commits to the server')
            print('  sgit status           — check vault state')

    def cmd_push(self, args):
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)

        if not token:
            token, base_url = self._prompt_remote_setup(args.directory, base_url)

        sync        = self.create_sync(base_url, token)
        branch_only = getattr(args, 'branch_only', False)
        progress    = CLI__Progress()
        remote_label = base_url or 'default'
        print(f'Pushing to {remote_label}...')
        result      = sync.push(args.directory, branch_only=branch_only,
                                on_progress=progress.callback)

        status = result.get('status', '')
        if status == 'up_to_date':
            print('Nothing to push — vault is already up to date.')
        elif status == 'pushed_branch_only':
            uploaded = result.get('objects_uploaded', 0)
            commits  = result.get('commits_pushed', 0)
            print()
            print(f'Pushed branch only: {commits} commit(s), {uploaded} object(s) uploaded.')
            print(f'  commit {result.get("commit_id", "")}')
            print(f'  branch ref {result.get("branch_ref_id", "")}')
            print()
            print('Next:')
            print('  sgit share            — share a snapshot with a simple token')
            print('  sgit status           — confirm vault state')
        else:
            uploaded = result.get('objects_uploaded', 0)
            commits  = result.get('commits_pushed', 0)
            print()
            print(f'Push complete. Named branch updated.')
            print(f'  Pushed {commits} commit(s), {uploaded} object(s) uploaded.')
            print(f'  commit {result.get("commit_id", "")}')
            print()
            print('Next:')
            print('  sgit share            — share a snapshot with a simple token')
            print('  sgit publish          — create a shareable encrypted archive')
            print('  sgit status           — confirm vault state')

    def _prompt_remote_setup(self, directory: str, base_url: str = None) -> tuple:
        """Interactive first-push setup: prompt for remote URL and auth token.

        Returns (token, base_url) tuple.
        """
        from sgit_ai.api.Vault__API import DEFAULT_BASE_URL

        print('No remote configured for this vault.')
        print()

        if not base_url:
            url_input = input(f'Remote URL [press Enter for {DEFAULT_BASE_URL}]: ').strip()
            base_url  = url_input or DEFAULT_BASE_URL

        token = input('Access token: ').strip()
        if not token:
            print('Error: an access token is required to push.', file=sys.stderr)
            sys.exit(1)

        # verify the token works by checking the API
        api = Vault__API(base_url=base_url, access_token=token)
        api.setup()
        try:
            vault_key = self.token_store.load_vault_key(directory)
            if vault_key:
                from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
                keys     = Vault__Crypto().derive_keys_from_vault_key(vault_key)
                vault_id = keys['vault_id']
                api.list_files(vault_id)                   # lightweight check — creates vault on first call
        except Exception as e:
            print(f'Warning: could not verify token ({e})', file=sys.stderr)

        self.token_store.save_token(token, directory)
        self.token_store.save_base_url(base_url, directory)
        print(f'Remote: {base_url}')
        print()
        return token, base_url

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

    # --- Remote management commands ---

    def cmd_remote_add(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.remote_add(args.directory, args.name, args.url, args.remote_vault_id)
        print(f'Added remote \'{result["name"]}\' -> {result["url"]} ({result["vault_id"]})')

    def cmd_remote_remove(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.remote_remove(args.directory, args.name)
        print(f'Removed remote \'{result["removed"]}\'')

    def cmd_remote_list(self, args):
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.remote_list(args.directory)
        remotes = result.get('remotes', [])
        if not remotes:
            print('No remotes configured.')
            return
        for r in remotes:
            print(f'  {r["name"]}\t{r["url"]} ({r["vault_id"]})')

    # --- Bare vault commands ---

    def cmd_checkout(self, args):
        vault_key = getattr(args, 'vault_key', None)
        if not vault_key:
            vault_key = self.token_store.load_vault_key(args.directory)
        if not vault_key:
            print('Error: --vault-key is required for bare vaults (no vault_key on disk).', file=sys.stderr)
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

    def cmd_vault_show_key(self, args):
        """Print the vault key for the vault in the given directory."""
        directory = getattr(args, 'directory', '.')
        vault_key = self.token_store.load_vault_key(directory)
        if not vault_key:
            print(f'Error: no vault key found in {directory}', file=sys.stderr)
            sys.exit(1)
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        keys     = Vault__Crypto().derive_keys_from_vault_key(vault_key)
        vault_id = keys['vault_id']
        print(f'Vault key:  {vault_key}')
        print(f'Vault ID:   {vault_id}')
        print()
        print('Keep your vault key safe — it is the only way to access your vault on another machine.')

    # --- Vault health ---

    def cmd_fsck(self, args):
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        progress = CLI__Progress()
        repair   = getattr(args, 'repair', False)

        print(f'Checking vault integrity in {args.directory}...')
        result = sync.fsck(args.directory, repair=repair, on_progress=progress.callback)

        if result.get('missing'):
            print(f'\n  Missing objects: {len(result["missing"])}')
            for oid in result['missing'][:10]:
                print(f'    ! {oid}')
            if len(result['missing']) > 10:
                print(f'    ... and {len(result["missing"]) - 10} more')

        if result.get('corrupt'):
            print(f'\n  Corrupt objects: {len(result["corrupt"])}')
            for oid in result['corrupt'][:10]:
                print(f'    ! {oid}')

        if result.get('errors'):
            print(f'\n  Errors:')
            for err in result['errors']:
                print(f'    ! {err}')

        if result.get('repaired'):
            print(f'\n  Repaired: {len(result["repaired"])} objects re-downloaded')

        if result['ok']:
            print('\nVault OK.')
        else:
            print('\nVault has problems.')
            if not repair:
                print('  hint: run "sgit fsck --repair" to attempt automatic repair')

    # --- Key derivation and inspection ---

    def cmd_derive_keys(self, args):
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(args.vault_key)
        print(f'vault_id:              {keys["vault_id"]}')
        print(f'read_key:              {keys["read_key"]}')
        print(f'write_key:             {keys["write_key"]}')
        print(f'ref_file_id:           {keys["ref_file_id"]}')
        print(f'branch_index_file_id:  {keys["branch_index_file_id"]}')

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
