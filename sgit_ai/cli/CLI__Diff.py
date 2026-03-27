import sys
from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Diff          import Vault__Diff


class CLI__Diff(Type_Safe):

    def cmd_diff(self, args):
        directory  = getattr(args, 'directory', '.') or '.'
        use_remote = getattr(args, 'remote',     False)
        commit_id  = getattr(args, 'commit',     None)
        files_only = getattr(args, 'files_only', False)

        diff = Vault__Diff(crypto=Vault__Crypto())

        try:
            if use_remote:
                result = diff.diff_vs_remote(directory)
            elif commit_id:
                result = diff.diff_vs_commit(directory, commit_id)
            else:
                result = diff.diff_vs_head(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        self._print_result(result, files_only)

    def _print_result(self, result, files_only: bool):
        mode_label = str(result.mode) if result.mode else 'HEAD'
        ref_label  = str(result.commit_id) if result.commit_id else mode_label.upper()

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
                            # Re-format header lines to show commit ref / working copy
                            lines = diff_text.splitlines(keepends=True)
                            formatted = []
                            for line in lines:
                                if line.startswith('--- '):
                                    formatted.append(f'--- {path}  (commit {ref_label})\n')
                                elif line.startswith('+++ '):
                                    formatted.append(f'+++ {path}  (working copy)\n')
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

        if parts:
            summary = ', '.join(parts)
            vs_label = f'vs {mode_label.upper()}'
            if result.commit_id:
                vs_label = f'vs commit {str(result.commit_id)[:12]}'
            print(f'{summary}  ({vs_label})')
        else:
            print(f'No changes  (vs {mode_label.upper()})')
