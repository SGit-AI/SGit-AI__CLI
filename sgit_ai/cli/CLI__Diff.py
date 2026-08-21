import json
import sys
from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.core.actions.diff.Vault__Diff          import Vault__Diff
from sgit_ai.cli._helpers              import parse_commit_range


class CLI__Diff(Type_Safe):
    vault_ref   : object = None   # CLI__Vault, injected by CLI__Main (on-demand fetch — A3)
    token_store : object = None   # injected by CLI__Main

    # --- A3: read-only on-demand fetch so inspecting one commit never needs a `pull` ---

    def _on_demand_api(self, directory: str, args):
        """Build a read-only api for on-demand fetch, or None if unavailable/offline.

        Gated on an explicitly-configured remote (named remote or `--base-url`) — a
        never-pushed local-only vault must NOT reach the default API host just
        because `history show`/`diff` hit a missing object (F3).
        """
        if self.vault_ref is None or self.token_store is None:
            return None
        try:
            remote = self.token_store.resolve_remote(args, directory)
            if not remote.get('name'):                    # '' = no real remote (F3)
                return None
            token  = self.token_store.resolve_token(getattr(args, 'token', None), directory)
            sync   = self.vault_ref.create_sync(remote['base_url'], token,
                                                tls_verify=remote['tls_verify'])
            return sync.api
        except Exception:
            return None

    def _try_fetch_commits(self, diff, directory: str, commit_ids: list, args) -> bool:
        """Read-only on-demand fetch of the given commits. True if any was fetched."""
        api = self._on_demand_api(directory, args)
        if api is None:
            return False
        diff.api = api
        fetched  = False
        for cid in [c for c in commit_ids if c]:
            try:
                print('  fetching missing history on demand (read-only)...', file=sys.stderr)
                if diff.ensure_commit_local(directory, cid):
                    fetched = True
            except Exception:
                pass
        return fetched

    def _exit_missing_object(self, e) -> None:
        print(f'error: {e}', file=sys.stderr)
        if 'obj-cas-imm-' in str(e) or 'bare/data' in str(e):
            print('  hint: object not cached locally and on-demand fetch unavailable — '
                  'run: sgit pull', file=sys.stderr)
        sys.exit(1)

    def cmd_log_range(self, args):
        """Handle `history log <from>..<to>` with optional --files / --patch / --json."""
        import datetime
        directory      = getattr(args, 'directory',  '.') or '.'
        range_spec     = getattr(args, 'range_spec', '') or ''
        oneline        = getattr(args, 'oneline',    False)
        include_files  = getattr(args, 'files',      False)
        include_patch  = getattr(args, 'patch',      False)
        json_out       = getattr(args, 'json_out',   False)
        limit          = getattr(args, 'limit',      None)

        from_commit, to_commit = parse_commit_range(range_spec)

        diff = Vault__Diff(crypto=Vault__Crypto())
        try:
            result = diff.log_range_with_details(
                directory,
                from_commit   = from_commit,
                to_commit     = to_commit,
                include_files = include_files or json_out,
                include_patch = include_patch,
                limit         = limit,
            )
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if json_out:
            print(json.dumps(result.json(), indent=2))
            return

        commits = result.commits
        if not commits:
            print('No commits in range.')
            return

        for entry in commits:
            cid      = str(entry.commit_id) if entry.commit_id else ''
            ts_iso   = str(entry.timestamp_iso) if entry.timestamp_iso else ''
            msg      = str(entry.message) if entry.message else ''
            short_id = cid[:24]
            short_ts = ts_iso[:10] if ts_iso else ''
            if oneline:
                print(f'{short_id}  {short_ts}  {msg}')
            else:
                print(f'commit {cid}')
                if entry.parent_ids:
                    print(f'parent {entry.parent_ids[0]}')
                print(f'Date:   {ts_iso}')
                if msg:
                    print()
                    print(f'    {msg}')
                print()

            if include_files and not oneline:
                for p in entry.files_added:
                    print(f'  + {p}')
                for p in entry.files_modified:
                    print(f'  ~ {p}')
                for p in entry.files_deleted:
                    print(f'  - {p}')
                if any([entry.files_added, entry.files_modified, entry.files_deleted]):
                    print()

            if include_patch and not oneline:
                patch = str(entry.patch) if entry.patch else ''
                if patch:
                    print(patch)

    def cmd_log_file(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        file_path = getattr(args, 'file_path', None)

        if not file_path:
            print('error: file path is required', file=sys.stderr)
            sys.exit(1)

        diff = Vault__Diff(crypto=Vault__Crypto())
        try:
            entries = diff.log_file(directory, file_path)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if not entries:
            print(f'No commits found that touched: {file_path}')
            return

        print(f'Commits touching: {file_path}')
        print()
        for entry in entries:
            status_sym = {'added': '+', 'modified': '~', 'deleted': '-'}.get(entry['status'], '?')
            msg        = entry['message'] or '(no message)'
            print(f'{status_sym} {entry["commit_id"]}  {entry["timestamp"]}  {msg}')

    def cmd_show(self, args):
        directory  = getattr(args, 'directory', '.') or '.'
        commit_id  = getattr(args, 'commit_id', None)
        files_only = getattr(args, 'files_only', False)

        if not commit_id:
            print('error: commit ID is required', file=sys.stderr)
            sys.exit(1)

        diff = Vault__Diff(crypto=Vault__Crypto())
        try:
            commit_info, result = diff.show_commit(directory, commit_id)
        except FileNotFoundError as e:
            if ('obj-cas-imm-' in str(e) or 'bare/data' in str(e)) \
                    and self._try_fetch_commits(diff, directory, [commit_id], args):
                try:
                    commit_info, result = diff.show_commit(directory, commit_id)
                except FileNotFoundError as e2:
                    self._exit_missing_object(e2)
            else:
                self._exit_missing_object(e)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        print(f'commit {commit_info["commit_id"]}')
        if commit_info['parent_id']:
            print(f'parent {commit_info["parent_id"]}')
        print(f'Date:   {commit_info["timestamp"]}')
        if commit_info['message']:
            print()
            print(f'    {commit_info["message"]}')
        print()

        self._print_result(result, files_only, raw_commit_a=commit_info['parent_id'],
                           raw_commit_b=commit_info['commit_id'])

    def cmd_diff(self, args):
        directory   = getattr(args, 'directory',  '.') or '.'
        use_remote  = getattr(args, 'remote',      False)
        commit_id   = getattr(args, 'commit',      None)
        commit_id2  = getattr(args, 'commit2',     None)
        files_only  = getattr(args, 'files_only',  False)
        json_out    = getattr(args, 'json_out',    False)
        range_spec  = getattr(args, 'range_spec',  '') or ''

        # Range syntax (positional <from>..<to>) overrides --commit / --commit2
        from sgit_ai.cli._helpers import looks_like_range
        if range_spec and looks_like_range(range_spec):
            from_c, to_c = parse_commit_range(range_spec)
            commit_id    = from_c or None
            commit_id2   = to_c   or None

        diff = Vault__Diff(crypto=Vault__Crypto())

        def _compute():
            if commit_id and commit_id2:
                if json_out:
                    result_obj = diff.diff_range(directory, commit_id, commit_id2,
                                                  include_patch=not files_only)
                    print(json.dumps(result_obj.json(), indent=2))
                    return None                       # printed-and-done sentinel
                return diff.diff_commits(directory, commit_id, commit_id2)
            elif use_remote:
                return diff.diff_vs_remote(directory)
            elif commit_id:
                return diff.diff_vs_commit(directory, commit_id)
            else:
                return diff.diff_vs_head(directory)

        try:
            result = _compute()
        except FileNotFoundError as e:
            targets = [c for c in (commit_id, commit_id2) if c]
            if ('obj-cas-imm-' in str(e) or 'bare/data' in str(e)) and targets \
                    and self._try_fetch_commits(diff, directory, targets, args):
                try:
                    result = _compute()
                except FileNotFoundError as e2:
                    self._exit_missing_object(e2)
            else:
                self._exit_missing_object(e)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if result is None:                            # json branch already printed
            return
        # Pass raw commit IDs from args so Safe_Str encoding doesn't mangle the labels
        self._print_result(result, files_only, raw_commit_a=commit_id, raw_commit_b=commit_id2)

    def _print_result(self, result, files_only: bool,
                      raw_commit_a: str = None, raw_commit_b: str = None):
        mode_label     = str(result.mode) if result.mode else 'HEAD'
        # Use raw commit strings from args when available (avoids Safe_Str encoding)
        commit_a       = raw_commit_a or (str(result.commit_id)   if result.commit_id   else '')
        commit_b       = raw_commit_b or (str(result.commit_id_b) if result.commit_id_b else '')
        is_two_commits = mode_label == 'commits' and commit_a and commit_b

        # Labels used in diff headers
        if is_two_commits:
            before_label = f'commit {commit_a}'
            after_label  = f'commit {commit_b}'
        else:
            before_label = f'commit {commit_a}' if commit_a else mode_label.upper()
            after_label  = 'working copy'

        for file_diff in result.files:
            status    = str(file_diff.status) if file_diff.status else ''
            path      = str(file_diff.path)   if file_diff.path   else ''
            is_binary = file_diff.is_binary

            if status == 'unchanged':
                continue

            if status == 'added':
                size = int(file_diff.size_after)
                print(f'+ {path}  ({size:,} bytes)')

            elif status == 'deleted':
                size = int(file_diff.size_before)
                print(f'- {path}  (was {size:,} bytes)')

            elif status == 'modified':
                if is_binary:
                    size_before = int(file_diff.size_before)
                    size_after  = int(file_diff.size_after)
                    h_before    = str(file_diff.hash_before) if file_diff.hash_before else ''
                    h_after     = str(file_diff.hash_after)  if file_diff.hash_after  else ''
                    print(f'~ {path}  (binary)')
                    print(f'    before: {size_before:,} bytes  sha256: {h_before}')
                    print(f'    after:  {size_after:,} bytes  sha256: {h_after}')
                else:
                    print(f'~ {path}')
                    if not files_only:
                        diff_text = str(file_diff.diff_text) if file_diff.diff_text else ''
                        if diff_text:
                            lines = diff_text.splitlines(keepends=True)
                            formatted = []
                            for line in lines:
                                if line.startswith('--- '):
                                    formatted.append(f'--- {path}  ({before_label})\n')
                                elif line.startswith('+++ '):
                                    formatted.append(f'+++ {path}  ({after_label})\n')
                                else:
                                    formatted.append(line)
                            print(''.join(formatted), end='')

        # Summary line
        m = int(result.modified_count)
        a = int(result.added_count)
        d = int(result.deleted_count)

        parts = []
        if m:
            parts.append(f'{m} modified')
        if a:
            parts.append(f'{a} added')
        if d:
            parts.append(f'{d} deleted')

        if is_two_commits:
            vs_label = f'{commit_a} → {commit_b}'
        elif commit_a:
            vs_label = f'vs commit {commit_a}'
        else:
            vs_label = f'vs {mode_label.upper()}'

        if parts:
            print(f'{", ".join(parts)}  ({vs_label})')
        else:
            print(f'No changes  ({vs_label})')
