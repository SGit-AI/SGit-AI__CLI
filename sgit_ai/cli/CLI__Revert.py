import sys

from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Revert        import Vault__Revert


class CLI__Revert(Type_Safe):

    def cmd_revert(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        commit_id = getattr(args, 'commit',    None)
        files     = getattr(args, 'files',     None) or []
        force     = getattr(args, 'force',     False)

        revert = Vault__Revert(crypto=Vault__Crypto())

        # Safety prompt when reverting all without --force
        if not files and not force:
            try:
                answer = input(f"This will discard ALL uncommitted changes in '{directory}'. Continue? [y/N]: ")
            except (EOFError, KeyboardInterrupt):
                print('\nAborted.')
                sys.exit(1)
            if answer.strip().lower() not in ('y', 'yes'):
                print('Aborted.')
                return

        try:
            if commit_id:
                result = revert.revert_to_commit(directory, commit_id, files or None)
                label  = f'commit {commit_id}'
            else:
                result = revert.revert_to_head(directory, files or None)
                cid    = result.get('commit_id') or 'HEAD'
                label  = f'HEAD (commit {cid[:12] if len(cid) > 12 else cid})'
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if not result.get('commit_id') and not result.get('restored') and not result.get('deleted'):
            print('Nothing to revert (no commits found).')
            return

        print(f'Reverting to {label}...')
        for path in result.get('restored', []):
            print(f'  restored  {path}')
        for path in result.get('deleted', []):
            print(f'  deleted   {path}')

        total = len(result.get('restored', [])) + len(result.get('deleted', []))
        print(f'\n{total} file(s) reverted.')
