import getpass
import os
import sys
import time
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.cli.CLI__Input                  import CLI__Input
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
        import shutil as _shutil
        from sgit_ai.transfer.Simple_Token import Simple_Token
        token     = self.token_store.resolve_token(getattr(args, 'token', None), None)
        base_url  = getattr(args, 'base_url', None)
        sync      = self.create_sync(base_url, token)
        vault_key = args.vault_key
        directory = args.directory
        force     = getattr(args, 'force', False)
        sparse    = getattr(args, 'sparse', False)
        read_key  = getattr(args, 'read_key', None)

        if not directory:
            token_str = vault_key.removeprefix('vault://')
            if Simple_Token.is_simple_token(token_str):
                directory = token_str
            else:
                parts    = vault_key.split(':')
                vault_id = parts[-1] if len(parts) == 2 else 'vault'
                directory = vault_id
        if force and sys.path and __import__('os').path.exists(directory):
            print(f'Removing existing \'{directory}\' (--force)...')
            _shutil.rmtree(directory)
        progress = CLI__Progress()

        if read_key:
            # Read-only clone: vault_key argument is used as vault_id
            vault_id_arg = vault_key.removeprefix('vault://')
            print(f'Cloning (read-only) into \'{directory}\'...')
            result = sync.clone_read_only(vault_id_arg, read_key, directory,
                                          on_progress=progress.callback, sparse=sparse)
            if token:
                self.token_store.save_token(token, result['directory'])
            if base_url:
                self.token_store.save_base_url(base_url, result['directory'])
            print()
            print(f'Read-only clone ready: {result["directory"]}/')
            print(f'  Vault ID:  {result["vault_id"]}')
            if result.get('commit_id'):
                print(f'  HEAD:      {result["commit_id"]}')
            print(f'  Mode:      read-only (no commit/push)')
            print()
            print('Next:')
            print(f'  cd {result["directory"]}')
            print( '  sgit ls              — list files')
            print( '  sgit cat <path>      — read a file')
            print( '  sgit fetch <path>    — download a file on demand')
            return

        if sparse:
            print(f'Sparse-cloning into \'{directory}\' (structure only, no file content)...')
        else:
            print(f'Cloning into \'{directory}\'...')
        result   = sync.clone(vault_key, directory, on_progress=progress.callback, sparse=sparse)
        effective_base_url = str(sync.api.base_url) if sync.api.base_url else ''

        # After a full clone, print read_key for future read-only clones
        keys = None
        try:
            keys = Vault__Crypto().derive_keys_from_vault_key(
                vault_key.removeprefix('vault://'))
        except Exception:
            pass

        if token:
            self.token_store.save_token(token, result['directory'])
        if effective_base_url:
            self.token_store.save_base_url(effective_base_url, result['directory'])
        print()
        if result.get('sparse'):
            print(f'Sparse clone ready: {result["directory"]}/')
        else:
            print(f'Cloned into {result["directory"]}/')
        print(f'  Vault ID:  {result["vault_id"]}')
        if result.get('share_token'):
            print(f'  From:      vault://{result["share_token"]}  (share token)')
            print(f'  Files:     {result.get("file_count", "?")} committed')
        if result.get('branch_id'):
            print(f'  Branch:    {result["branch_id"]}')
        if result.get('commit_id'):
            print(f'  HEAD:      {result["commit_id"]}')
        if keys and keys.get('read_key'):
            print(f'  Read key:  {keys["read_key"]}  (share for read-only access)')
        print()
        print('Next:')
        print(f'  cd {result["directory"]}')
        if result.get('sparse'):
            print( '  sgit ls              — list files (· = remote only, ✓ = local)')
            print( '  sgit fetch <path>    — download a file or directory on demand')
            print( '  sgit cat <path>      — read a file without saving to disk')
            print( '  sgit fetch           — download everything (convert to full clone)')
        else:
            print( '  ls                   — view files')
            print( '  sgit status          — check vault state')
            print( '  sgit log             — view commit history')
        if result.get('share_token'):
            print( '  sgit share           — re-publish (same URL, updated content)')
            print( '  sgit push            — push to SGit-AI to enable collaboration')
        else:
            print( '  sgit push            — push to SGit-AI')
            print( '  sgit share           — share a read-only snapshot')

    def cmd_init(self, args):
        import glob as _glob
        from sgit_ai.transfer.Simple_Token         import Simple_Token
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist
        sync       = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        vault_key  = getattr(args, 'vault_key', None) or None
        directory  = args.directory
        restore    = getattr(args, 'restore', False)
        existing   = getattr(args, 'existing', False)

        # Allow `sgit init coral-equal-1234` — if directory arg is a simple token, treat it as token
        if directory and Simple_Token.is_simple_token(directory):
            if not vault_key:
                vault_key = directory
                directory = vault_key   # vault dir will be named after token

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
            answer = CLI__Input().prompt('Restore vault from this backup? [Y/n]: ')
            if answer is None or answer.strip().lower() in ('n', 'no'):
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
                answer = CLI__Input().prompt(f"Directory '{directory}' is not empty ({n} file(s) found).\n"
                                             f'Initialise vault here anyway? [y/N]: ')
                if answer is None or answer.strip().lower() not in ('y', 'yes'):
                    print('Init cancelled.')
                    return
                existing = True

        # Simple token handling: if vault_key is a simple token, use token= arg
        init_token = None
        if vault_key and Simple_Token.is_simple_token(vault_key):
            init_token = vault_key
            vault_key  = None
        elif not vault_key and directory in ('.', '') and not restore:
            # Scenario C: bare `sgit init` → auto-generate a simple token
            generated  = Simple_Token__Wordlist().setup().generate()
            init_token = str(generated)
            directory  = init_token   # use token as directory name

        result = sync.init(directory, vault_key=vault_key, allow_nonempty=existing,
                           token=init_token)
        token  = getattr(args, 'token', None)
        if token:
            self.token_store.save_token(token, result['directory'])

        is_simple = result.get('vault_id') == (init_token or result.get('vault_id', ''))
        simple_token_mode = init_token is not None and Simple_Token.is_simple_token(result['vault_id'])

        print(f'Vault created!  Vault ID: {result["vault_id"]}')
        print(f'  Directory: {result["directory"]}/')
        if simple_token_mode:
            print(f'  Edit token: {result["vault_id"]}')
            print(f'  (Share with collaborators using: sgit clone {result["vault_id"]})')
        else:
            print(f'  Vault key: {result["vault_key"]}')
        print(f'  Branch:    {result["branch_id"]}')
        print()
        if simple_token_mode:
            print('  Your edit token IS your vault key — keep it safe.')
        else:
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
                answer = CLI__Input().prompt('Commit all existing files now? [Y/n]: ')
                if answer is not None and answer.strip().lower() not in ('n', 'no'):
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

    def _check_read_only(self, directory: str):
        """Raise RuntimeError if the vault is a read-only clone."""
        clone_mode = self.token_store.load_clone_mode(directory)
        if clone_mode.get('mode') == 'read-only':
            raise RuntimeError('This vault was cloned read-only. To write, re-clone with the full vault key.')

    def cmd_commit(self, args):
        self._check_read_only(args.directory)
        sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        message = getattr(args, 'message', '') or ''
        try:
            result = sync.commit(args.directory, message=message)
        except RuntimeError as e:
            if 'nothing to commit' in str(e):
                print('Nothing to commit, working tree clean.')
                return
            raise
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
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        result   = sync.status(args.directory)
        explain = getattr(args, 'explain', False)

        clone_branch_id   = result.get('clone_branch_id', '')
        named_branch_id   = result.get('named_branch_id', '')
        push_status       = result.get('push_status', 'unknown')
        ahead             = result.get('ahead', 0)
        behind            = result.get('behind', 0)
        remote_configured = result.get('remote_configured', False)
        never_pushed      = result.get('never_pushed', False)

        if result.get('sparse'):
            fetched = result.get('files_fetched', 0)
            total   = result.get('files_total', 0)
            unfetched = total - fetched
            print(f'Sparse mode: {fetched}/{total} file(s) fetched locally')
            if unfetched:
                print(f'  {unfetched} file(s) available on server — run: sgit fetch <path>')
            print()

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

    def cmd_reset(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        commit_id = getattr(args, 'commit_id', None)
        sync      = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result    = sync.reset(directory, commit_id)
        short     = result['commit_id'][:24]
        if commit_id is None:
            print(f'Working copy restored to HEAD ({short})')
            print(f'  {result["restored"]} file(s) restored, {result["deleted"]} removed.')
        else:
            print(f'HEAD reset to {short}')
            print(f'  {result["restored"]} file(s) restored, {result["deleted"]} removed.')
            print()
            print('To rewrite the remote branch:')
            print('  sgit push --force')

    def cmd_push(self, args):
        self._check_read_only(args.directory)
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)

        if not token:
            token, base_url = self._prompt_remote_setup(args.directory, base_url)

        sync        = self.create_sync(base_url, token)
        branch_only = getattr(args, 'branch_only', False)
        force       = getattr(args, 'force', False)
        progress    = CLI__Progress()
        remote_label = base_url or 'default'
        if force:
            print(f'Force-pushing to {remote_label}...')
        else:
            print(f'Pushing to {remote_label}...')
        result      = sync.push(args.directory, branch_only=branch_only, force=force,
                                on_progress=progress.callback)

        status = result.get('status', '')
        if status == 'resynced':
            print('Vault structure re-synced to server.')
        elif status == 'up_to_date':
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
        Aborts (sys.exit) if stdin is not a TTY or the user does not respond
        within 30 seconds — never hangs in non-interactive contexts.
        """
        from sgit_ai.api.Vault__API import DEFAULT_BASE_URL

        inp = CLI__Input()

        if not sys.stdin.isatty():
            print('Error: no access token configured. Pass --token or run '
                  '`sgit auth` to save credentials.', file=sys.stderr)
            sys.exit(1)

        print('No remote configured for this vault.')
        print()

        if not base_url:
            url_input = inp.prompt(f'Remote URL [press Enter for {DEFAULT_BASE_URL}]: ')
            if url_input is None:
                print('Error: setup cancelled — no access token provided.', file=sys.stderr)
                sys.exit(1)
            base_url = url_input.strip() or DEFAULT_BASE_URL

        token_raw = inp.prompt('Access token: ')
        if token_raw is None:
            print('Error: setup cancelled — no access token provided.', file=sys.stderr)
            sys.exit(1)
        token = token_raw.strip()
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

    def create_transfer_api(self, base_url: str = None) -> 'API__Transfer':
        from sgit_ai.api.API__Transfer import API__Transfer, DEFAULT_BASE_URL as TRANSFER_BASE_URL
        api = API__Transfer(base_url=base_url or TRANSFER_BASE_URL)
        api.setup()
        return api

    def cmd_share(self, args):
        """Publish or refresh a read-only SG/Send snapshot for a simple_token vault."""
        import json as _json
        from sgit_ai.transfer.Simple_Token          import Simple_Token
        from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist
        from sgit_ai.transfer.Vault__Transfer        import Vault__Transfer
        from sgit_ai.storage.Vault__Storage             import Vault__Storage

        directory  = getattr(args, 'directory', '.') or '.'
        rotate     = getattr(args, 'rotate', False)
        token_str  = getattr(args, 'token', None)
        base_url   = getattr(args, 'base_url', None)

        storage     = Vault__Storage()
        config_path = storage.local_config_path(directory)
        if not __import__('os').path.isfile(config_path):
            print(f'error: not a vault directory: {directory}', file=sys.stderr)
            sys.exit(1)

        with open(config_path, 'r') as f:
            config_data = _json.load(f)

        mode = config_data.get('mode', '')
        if mode != 'simple_token':
            print('error: sgit share requires a simple_token vault', file=sys.stderr)
            print('  hint: initialise with: sgit init <word-word-NNNN>', file=sys.stderr)
            sys.exit(1)

        # Determine share token to use
        if token_str:
            share_token = token_str
        elif rotate or not config_data.get('share_token'):
            share_token = str(Simple_Token__Wordlist().setup().generate())
        else:
            share_token = config_data['share_token']

        api      = self.create_transfer_api(base_url)
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())

        print('Publishing snapshot...')
        result = transfer.share(directory, token_str=share_token)

        config_data['share_token']       = share_token
        config_data['share_transfer_id'] = result['transfer_id']
        with open(config_path, 'w') as f:
            _json.dump(config_data, f, indent=2)

        file_count  = result['file_count']
        total_kb    = result['total_bytes'] / 1024
        print(f'  Files:   {file_count} file(s), {total_kb:.1f} KB')
        print()
        print(f'Published: https://send.sgraph.ai/#{share_token}')

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
            head   = b['head_commit'] if b['head_commit'] else '(none)'
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
        import re
        from sgit_ai.sync.Vault__Branch_Switch import Vault__Branch_Switch
        from sgit_ai.sync.Vault__Revert        import Vault__Revert

        target    = getattr(args, 'target', None)
        directory = args.directory
        force     = getattr(args, 'force', False)

        # If a target is provided and the vault is a normal (non-bare) vault,
        # route to branch-switch, HEAD restore, or commit-revert.
        if target:
            local_vault_key_path = os.path.join(directory, '.sg_vault', 'local', 'vault_key')
            if os.path.isfile(local_vault_key_path):
                _BRANCH_RE = re.compile(r'^branch-(named|clone)-[0-9a-f]{8,64}$')
                _HEX_RE    = re.compile(r'^[0-9a-f]{8,64}$')
                revert_obj = Vault__Revert(crypto=Vault__Crypto())

                # "HEAD" → restore working copy from clone branch HEAD (undo detached state)
                if target.upper() == 'HEAD':
                    try:
                        result   = revert_obj.revert_to_head(directory)
                        commit   = result.get('commit_id', '')
                        restored = len(result.get('restored', []))
                        deleted  = len(result.get('deleted',  []))
                        print(f'Restored to HEAD  ({commit})')
                        print(f'  {restored} file(s) restored, {deleted} removed.')
                        return
                    except (FileNotFoundError, RuntimeError) as e:
                        print(f'error: {e}', file=sys.stderr)
                        sys.exit(1)

                switcher = Vault__Branch_Switch(crypto=Vault__Crypto())

                if _BRANCH_RE.match(target) or not _HEX_RE.match(target):
                    # Looks like a branch ID or name → try switch
                    try:
                        result = switcher.switch(directory, target, force=force)
                        named_name = result['named_name']
                        new_clone  = result['new_clone_branch_id']
                        files      = result['files_restored']
                        reused     = result.get('reused', False)
                        action     = 'Resumed' if reused else 'Switched to'
                        print(f"{action} branch '{named_name}'  ({new_clone})")
                        print(f'  {files} file(s) checked out.')
                        return
                    except RuntimeError as e:
                        if 'Branch not found' not in str(e) or _BRANCH_RE.match(target):
                            print(f'error: {e}', file=sys.stderr)
                            sys.exit(1)
                        # Fall through to commit-revert if the target might be a short hex ID

                # Looks like a commit ID (full or prefix)
                try:
                    result   = revert_obj.revert_to_commit(directory, target)
                    commit   = result.get('commit_id', target)
                    restored = len(result.get('restored', []))
                    deleted  = len(result.get('deleted',  []))
                    print(f'HEAD detached at {commit}')
                    print(f'  {restored} file(s) restored, {deleted} removed.')
                    print('  (use: sgit checkout HEAD  to return to the current branch state)')
                    return
                except (FileNotFoundError, RuntimeError) as e:
                    print(f'error: {e}', file=sys.stderr)
                    sys.exit(1)

        # Bare vault path (no target, or no local vault_key)
        vault_key = getattr(args, 'vault_key', None)
        if not vault_key:
            vault_key = self.token_store.load_vault_key(directory)
        if not vault_key:
            print('Error: --vault-key is required for bare vaults (no saved key found).', file=sys.stderr)
            sys.exit(1)
        bare = Vault__Bare(crypto=Vault__Crypto())
        bare.checkout(directory, vault_key)
        files = bare.list_files(directory, vault_key)
        print(f'Checked out {len(files)} files to {directory}/')

    def cmd_clean(self, args):
        empty_dirs = getattr(args, 'empty_dirs', False)
        if empty_dirs:
            sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
            removed = sync._remove_empty_dirs(args.directory)
            if removed:
                for d in removed:
                    print(f'  removed {d}/')
                print(f'Removed {len(removed)} empty director{"ies" if len(removed) != 1 else "y"}.')
            else:
                print('No empty directories found.')
            return
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

    def cmd_info(self, args):
        """Show vault identity, remote configuration, branch status, and web URL."""
        import os
        from sgit_ai._version         import VERSION
        from sgit_ai.api.Vault__API   import DEFAULT_BASE_URL

        directory = getattr(args, 'directory', '.')
        directory = os.path.abspath(directory)

        from sgit_ai.transfer.Simple_Token import Simple_Token

        clone_mode = self.token_store.load_clone_mode(directory)
        is_read_only = clone_mode.get('mode') == 'read-only'

        if is_read_only:
            vault_id = clone_mode.get('vault_id', '')
            read_key = clone_mode.get('read_key', '')
            base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), directory)
            if not base_url:
                base_url = DEFAULT_BASE_URL
            print(f'Vault directory: {directory}')
            print(f'  Vault ID:    {vault_id}')
            print(f'  Mode:        read-only (no commit/push)')
            print(f'  Read key:    {read_key}')
            print(f'  Write key:   ✗ not available  (re-clone with full vault key to write)')
            print()
            print('Remote:')
            print(f'  URL:         {base_url}')
            print()
            print(f'Version: {VERSION}')
            return

        vault_key = self.token_store.load_vault_key(directory)
        if not vault_key:
            print(f'Error: no vault key found in {directory}', file=sys.stderr)
            sys.exit(1)

        crypto           = Vault__Crypto()
        is_simple_token  = Simple_Token.is_simple_token(vault_key)
        keys             = crypto.derive_keys_from_vault_key(vault_key)
        vault_id         = keys['vault_id']
        read_key         = keys.get('read_key', '')

        if is_simple_token:
            # Combined format lets the vault be opened with either the plain
            # token OR the "token:vault_id" standard key — both are equivalent.
            passphrase       = vault_key
            full_vault_key   = f'{vault_key}:{vault_id}'
        else:
            passphrase       = keys['passphrase']
            full_vault_key   = vault_key

        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), directory)
        if not base_url:
            base_url = DEFAULT_BASE_URL

        # Web URL always uses the human-memorable form (token for simple-token vaults)
        web_url = base_url.replace('send.sgraph.ai', 'vault.sgraph.ai') + '/en-gb/#' + vault_key

        token_configured = bool(self.token_store.load_token(directory))

        # Get branch status via sync (no API call needed)
        sync   = self.create_sync(base_url, None)
        status = sync.status(directory)

        clone_branch = status.get('clone_branch_id', '') or 'local'
        named_branch = status.get('named_branch_id', '') or 'current'
        clone_head   = status.get('clone_head') or ''
        push_status  = status.get('push_status', 'unknown')

        push_status_label = {
            'up_to_date': 'up to date',
            'ahead':      f'ahead by {status.get("ahead", 0)} commit(s)',
            'behind':     f'behind by {status.get("behind", 0)} commit(s)',
            'diverged':   'diverged',
            'unknown':    'unknown',
        }.get(push_status, push_status)

        print(f'Vault directory: {directory}')
        print(f'  Vault ID:    {vault_id}')
        if is_simple_token:
            print(f'  Passphrase:  {passphrase}')
            print(f'  Vault key:   {full_vault_key}   (passphrase:vault_id — either form works)')
        else:
            print(f'  Passphrase:  {passphrase}')
            print(f'  Vault key:   {full_vault_key}')
        if read_key:
            print(f'  Read key:    {read_key}  (share for read-only access)')
        print(f'  Write key:   ✓ available')
        print(f'  Web URL:     {web_url}')
        print()
        print('Remote:')
        print(f'  URL:         {base_url}')
        print(f'  Token:       {"configured" if token_configured else "not configured"}')
        print()
        print('Branch:')
        print(f'  Current:     {clone_branch}  →  {named_branch}')
        if clone_head:
            print(f'  HEAD:        {clone_head}')
        print(f'  Status:      {push_status_label}')
        print()
        print(f'Version: {VERSION}')

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

    # --- Token probe and key derivation ---

    def cmd_probe(self, args):
        """Identify a simple token as a vault or share without cloning."""
        import json as _json
        as_json        = getattr(args, 'json', False)
        resolved_token = self.token_store.resolve_token(getattr(args, 'token_flag', None), None)
        base_url       = getattr(args, 'base_url', None)
        sync           = self.create_sync(base_url, resolved_token or None)
        result         = sync.probe_token(args.token)
        token          = result['token']

        if as_json:
            print(_json.dumps(result))
            return

        if result['type'] == 'vault':
            print(f'vault   {token}')
            print(f'  Vault ID:     {result["vault_id"]}')
            print()
            print('Next:')
            print(f'  sgit clone --sparse {token}   — clone structure only')
            print(f'  sgit clone {token}            — full clone')
        else:
            print(f'share   {token}')
            print(f'  Transfer ID:  {result["transfer_id"]}')
            print()
            print('Next:')
            print(f'  sgit clone {token}   — download snapshot')

    def cmd_delete_on_remote(self, args):
        """Hard-delete vault from server, leaving local clone intact."""
        import json as _json
        import sys
        directory = args.directory
        as_json   = getattr(args, 'json', False)
        sync      = self.create_sync()
        c         = sync._init_components(directory)
        if not c.write_key:
            raise RuntimeError('This is a read-only clone — cannot delete a vault without write access.')
        if not getattr(args, 'yes', False):
            print(f'About to permanently delete vault {c.vault_id} from the server.')
            print('This cannot be undone. The local clone will be kept intact.')
            print(f'Type the vault ID to confirm: ', end='', flush=True)
            answer = sys.stdin.readline().strip()
            if answer != c.vault_id:
                raise RuntimeError('Vault ID did not match — aborting.')
        result = sync.delete_on_remote(directory)
        if as_json:
            print(_json.dumps(result))
            return
        files_deleted = result.get('files_deleted', 0)
        if files_deleted == 0:
            print(f'Vault {c.vault_id} was already absent from the server.')
        else:
            print(f'Deleted vault {c.vault_id} from the server ({files_deleted} files removed).')
        print()
        print('Local clone is intact. Next steps:')
        print('  sgit rekey    — re-encrypt with a new vault key, then sgit push')
        print('  sgit push     — re-publish this vault with the same key')

    # --- Rekey wizard and sub-steps ---

    def cmd_rekey(self, args):
        """Interactive key-rotation wizard: asks questions, shows progress."""
        import json as _json
        import sys

        directory = args.directory
        new_key   = getattr(args, 'new_key', None)
        as_json   = getattr(args, 'json', False)
        skip      = getattr(args, 'yes', False)
        sync      = self.create_sync()

        W = '━' * 44
        print(W)
        print(' sgit rekey — Key Rotation Wizard')
        print(W)
        print()

        info = sync.rekey_check(directory)
        print('Current vault')
        print(f'  Directory : {directory}')
        print(f'  Vault ID  : {info["vault_id"]}')
        print(f'  Files     : {info["file_count"]}')
        print(f'  Objects   : {info["obj_count"]} encrypted objects in .sg_vault/')
        print(f'  Status    : {"clean" if info["clean"] else "⚠  uncommitted changes"}')
        print()

        print('What this will do:')
        print('  1  Wipe local encrypted store (.sg_vault/)')
        print('  2  Create a new vault key and vault ID')
        print(f'  3  Re-encrypt all {info["file_count"]} file(s) under the new key')
        print('  Note: commit history resets to a single commit.')
        print()

        if not skip:
            print('Before continuing — answer both questions:')
            print()
            print('  Have you run "sgit delete-on-remote" first?')
            print('  (If the vault still exists on the server, the old key remains valid there.)')
            print('  [y/N] ', end='', flush=True)
            if sys.stdin.readline().strip().lower() not in ('y', 'yes'):
                raise RuntimeError('Aborted — run "sgit delete-on-remote" first.')
            print()
            print('  Have you saved your current vault key somewhere safe?')
            print(f'  Key starts with: {info["vault_id"][:8]}...')
            print('  [y/N] ', end='', flush=True)
            if sys.stdin.readline().strip().lower() not in ('y', 'yes'):
                raise RuntimeError('Aborted — save your vault key before continuing.')
            print()
            print('  Type  YES  to begin key rotation: ', end='', flush=True)
            if sys.stdin.readline().strip() != 'YES':
                raise RuntimeError('Aborted.')
            print()

        print(f'  [1/3] Wiping local encrypted store...', end='', flush=True)
        wipe_r = sync.rekey_wipe(directory)
        print(f'   done  ({wipe_r["objects_removed"]} objects removed)')

        print(f'  [2/3] Initialising new vault...      ', end='', flush=True)
        init_r = sync.rekey_init(directory, new_vault_key=new_key)
        print(f'   done')

        print(f'  [3/3] Re-encrypting files...         ', end='', flush=True)
        commit_r = sync.rekey_commit(directory)
        print(f'   done  ({commit_r["file_count"]} file(s))')
        print()

        if as_json:
            print(_json.dumps(dict(vault_key=init_r['vault_key'],
                                   vault_id=init_r['vault_id'],
                                   commit_id=commit_r['commit_id'])))
            return

        bar = '─' * 44
        print(W)
        print(' Rekey complete')
        print(W)
        print(f'  New vault ID: {init_r["vault_id"]}')
        print()
        print(f'  {bar}')
        print(f'  SAVE YOUR NEW VAULT KEY — cannot be recovered:')
        print()
        print(f'    {init_r["vault_key"]}')
        print(f'  {bar}')
        print()
        print('Next:')
        print('  sgit push   — publish the vault under the new key')

    def cmd_rekey_check(self, args):
        """Show vault state without making any changes."""
        import json as _json
        directory = args.directory
        sync      = self.create_sync()
        info      = sync.rekey_check(directory)
        if getattr(args, 'json', False):
            print(_json.dumps(info))
            return
        print('Vault state (no changes made)')
        print(f'  Directory : {directory}')
        print(f'  Vault ID  : {info["vault_id"]}')
        print(f'  Files     : {info["file_count"]}')
        print(f'  Objects   : {info["obj_count"]} encrypted objects in .sg_vault/')
        print(f'  Status    : {"clean" if info["clean"] else "uncommitted changes present"}')
        print()
        print('Rekey will:')
        print(f'  - Remove {info["obj_count"]} objects from .sg_vault/')
        print(f'  - Generate a new vault key and vault ID')
        print(f'  - Re-encrypt {info["file_count"]} file(s)')

    def cmd_rekey_wipe(self, args):
        """Wipe the local encrypted store. Working files are not touched."""
        import sys
        directory = args.directory
        sync      = self.create_sync()
        if not getattr(args, 'yes', False):
            info = sync.rekey_check(directory)
            print(f'Wipe encrypted store for vault {info["vault_id"]}?')
            print(f'  This removes .sg_vault/ ({info["obj_count"]} objects). Working files are kept.')
            print('  Type YES to continue: ', end='', flush=True)
            if sys.stdin.readline().strip() != 'YES':
                raise RuntimeError('Aborted.')
        result = sync.rekey_wipe(directory)
        print(f'Wiped. {result["objects_removed"]} objects removed.')
        print()
        print('Next:')
        print('  sgit rekey init           — re-initialise with a generated key')
        print('  sgit rekey init --new-key your:customkey8')

    def cmd_rekey_init(self, args):
        """Re-initialise vault structure with a new key."""
        directory = args.directory
        new_key   = getattr(args, 'new_key', None)
        sync      = self.create_sync()
        print('Initialising new vault...', end='', flush=True)
        result = sync.rekey_init(directory, new_vault_key=new_key)
        print(' done')
        print()
        print(f'New vault ID: {result["vault_id"]}')
        print()
        bar = '─' * 44
        print(f'  {bar}')
        print('  SAVE YOUR NEW VAULT KEY — cannot be recovered:')
        print()
        print(f'    {result["vault_key"]}')
        print(f'  {bar}')
        print()
        print('Next:')
        print('  sgit rekey commit   — re-encrypt all files')

    def cmd_rekey_commit(self, args):
        """Commit all working-directory files under the current key."""
        directory = args.directory
        sync      = self.create_sync()
        print('Re-encrypting files...', end='', flush=True)
        result = sync.rekey_commit(directory)
        file_count = result['file_count']
        print(f' done  ({file_count} file(s))')
        if result['commit_id']:
            print(f'  Commit: {result["commit_id"]}')
        print()
        print('Next:')
        print('  sgit push   — publish the vault under the new key')

    def cmd_derive_keys(self, args):
        import re as _re
        from sgit_ai.transfer.Simple_Token import Simple_Token
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        crypto    = Vault__Crypto()
        token_str = args.vault_key.removeprefix('vault://')

        # read_key:vault_id format — 64-char hex key with a vault_id suffix
        if _re.match(r'^[0-9a-f]{64}:[a-z0-9]{4,24}$', token_str):
            hex_key, vault_id_part = token_str.split(':', 1)
            imported = crypto.import_read_key(hex_key, vault_id_part)
            print(f'vault_id:              {imported["vault_id"]}')
            print(f'read_key:              {imported["read_key"]}')
            print()
            print('Note: write_key, ref_file_id, and branch_index_file_id are not derivable')
            print('      from a read_key alone. Re-clone with the full vault key to access them.')
            return

        keys   = crypto.derive_keys_from_vault_key(token_str)
        print(f'vault_id:              {keys["vault_id"]}')
        print(f'read_key:              {keys["read_key"]}')
        print(f'write_key:             {keys["write_key"]}')
        print(f'ref_file_id:           {keys["ref_file_id"]}')
        print(f'branch_index_file_id:  {keys["branch_index_file_id"]}')
        if Simple_Token.is_simple_token(token_str):
            st = Simple_Token(token=Safe_Str__Simple_Token(token_str))
            print()
            print(f'--- SG/Send (simple token) ---')
            print(f'transfer_id:           {st.transfer_id()}')
            print(f'send_aes_key:          {st.aes_key().hex()}')

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
        oneline   = getattr(args, 'oneline', False)
        graph     = getattr(args, 'graph', False)
        if graph:
            # Full DAG walk (all parents) for graph mode
            chain = inspector.inspect_commit_dag(args.directory, read_key=read_key)
        else:
            chain = inspector.inspect_commit_chain(args.directory, read_key=read_key)
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
        if not getattr(args, 'graph', False):
            args.oneline = True
        self.cmd_inspect_log(args)

    # --- sparse / on-demand commands ---

    def cmd_ls(self, args):
        """List vault tree entries with fetch status (works for sparse and full clones)."""
        import json as _json
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        path     = getattr(args, 'path', None) or None
        show_ids = getattr(args, 'ids', False)
        as_json  = getattr(args, 'json', False)
        entries  = sync.sparse_ls(args.directory, path=path)

        if as_json:
            print(_json.dumps(entries, indent=2))
            return

        if not entries:
            print('(empty vault or path not found)')
            return

        fetched_count = sum(1 for e in entries if e['fetched'])
        total         = len(entries)

        for e in entries:
            status  = '✓' if e['fetched'] else '·'
            size_kb = f'{e["size"] / 1024:.1f}K' if e['size'] >= 1024 else f'{e["size"]}B'
            if show_ids:
                print(f'  {status}  {size_kb:>8}  {e["blob_id"]}  {e["path"]}')
            else:
                print(f'  {status}  {size_kb:>8}  {e["path"]}')

        print()
        print(f'  {fetched_count}/{total} file(s) fetched locally')
        if fetched_count < total:
            print('  · = remote only  (run: sgit fetch <path>  to download)')

    def cmd_fetch(self, args):
        """Fetch one or more files from the server into the working copy."""
        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        path     = getattr(args, 'path', None) or None
        fetch_all = getattr(args, 'all', False)
        progress  = CLI__Progress()

        label = 'all files' if (fetch_all or not path) else f"'{path}'"
        print(f'Fetching {label}...')
        result = sync.sparse_fetch(args.directory, path=path, on_progress=progress.callback)

        fetched  = result.get('fetched', 0)
        already  = result.get('already_local', 0)
        written  = result.get('written', [])

        print()
        for p in written:
            print(f'  ✓  {p}')

        if fetched == 0 and already > 0:
            print(f'Already fetched ({already} file(s) up to date).')
        elif fetched == 0:
            print('No files matched.')
        else:
            print(f'\nFetched {fetched} file(s), {already} already local.')

    def cmd_cat(self, args):
        """Decrypt and print a vault file to stdout (fetches from server if not cached)."""
        import json as _json
        show_id  = getattr(args, 'id',   False)
        as_json  = getattr(args, 'json', False)

        if show_id or as_json:
            # Zero-network metadata path — look up flat map entry
            token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
            base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
            sync     = self.create_sync(base_url, token)
            entries  = sync.sparse_ls(args.directory, path=args.path)
            match    = next((e for e in entries if e['path'] == args.path), None)
            if not match:
                print(f'error: path not found in vault: {args.path}', file=sys.stderr)
                sys.exit(1)
            if show_id:
                print(match['blob_id'])
            else:
                print(_json.dumps(dict(path         = match['path'],
                                       blob_id      = match['blob_id'],
                                       size         = match['size'],
                                       content_type = match.get('content_type', ''),
                                       fetched      = match['fetched']),
                                  indent=2))
            return

        token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
        base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
        sync     = self.create_sync(base_url, token)
        content  = sync.sparse_cat(args.directory, args.path)
        sys.stdout.buffer.write(content)

    def cmd_write(self, args):
        """Write a file directly to vault HEAD (agent/programmatic workflow)."""
        import json as _json
        self._check_read_only(args.directory)

        path    = args.path
        as_json = getattr(args, 'json', False)
        message = getattr(args, 'message', '') or ''
        do_push = getattr(args, 'push',    False)
        file_   = getattr(args, 'file',    None)
        also_   = getattr(args, 'also',    []) or []

        # Read primary content
        if file_:
            with open(file_, 'rb') as f:
                content = f.read()
        else:
            content = sys.stdin.buffer.read()

        # Parse --also vault_path:local_file pairs
        also_map = {}
        for spec in also_:
            if ':' not in spec:
                print(f'error: --also requires VAULT_PATH:LOCAL_FILE format, got: {spec}',
                      file=sys.stderr)
                sys.exit(1)
            v_path, l_file = spec.split(':', 1)
            with open(l_file, 'rb') as f:
                also_map[v_path] = f.read()

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.write_file(args.directory, path, content,
                                 message=message, also=also_map or None)

        if do_push:
            token    = self.token_store.resolve_token(getattr(args, 'token', None), args.directory)
            base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), args.directory)
            if not token:
                token, base_url = self._prompt_remote_setup(args.directory, base_url)
            sync2    = self.create_sync(base_url, token)
            progress = CLI__Progress()
            sync2.push(args.directory, on_progress=progress.callback)
            print(file=sys.stderr)
            print('Pushed.', file=sys.stderr)

        blob_id = result.get('blob_id', '')
        if as_json:
            print(_json.dumps(dict(blob_id   = blob_id,
                                   commit_id = result.get('commit_id', ''),
                                   message   = result.get('message', ''),
                                   unchanged = result.get('unchanged', False),
                                   paths     = result.get('paths', {}))))
        else:
            print(blob_id)
