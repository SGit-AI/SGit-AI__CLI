import sys
from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Diff          import Vault__Diff


class CLI__Diff(Type_Safe):

    def cmd_diff(self, args):
        directory  = getattr(args, 'directory', '.') or '.'
        use_remote = getattr(args, 'remote',     False)
        commit_id  = getattr(args, 'commit',     None)
        commit_id2 = getattr(args, 'commit2',    None)
        files_only = getattr(args, 'files_only', False)

        diff = Vault__Diff(crypto=Vault__Crypto())

        try:
            if commit_id and commit_id2:
                result = diff.diff_commits(directory, commit_id, commit_id2)
            elif use_remote:
                result = diff.diff_vs_remote(directory)
            elif commit_id:
                result = diff.diff_vs_commit(directory, commit_id)
            else:
                result = diff.diff_vs_head(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            if 'bare/data' in str(e):
                print('  hint: object not cached locally — run: sgit pull  to fetch missing history',
                      file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

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
