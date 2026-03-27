import sys

from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Stash         import Vault__Stash


class CLI__Stash(Type_Safe):

    def cmd_stash(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        stash     = Vault__Stash(crypto=Vault__Crypto())

        try:
            result = stash.stash(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if result.get('nothing_to_stash'):
            print('Nothing to stash.')
            return

        status     = result.get('status', {})
        added      = status.get('added', [])
        modified   = status.get('modified', [])
        deleted    = status.get('deleted', [])
        total      = len(added) + len(modified) + len(deleted)
        stash_path = result.get('stash_path', '')
        meta       = result.get('meta')
        commit_id  = str(meta.base_commit) if meta and meta.base_commit else 'HEAD'

        print(f'Stashing {total} changes...')
        for path in modified:
            print(f'  ~ {path}')
        for path in added:
            print(f'  + {path}')
        for path in deleted:
            print(f'  - {path}')

        import os
        print(f'\nStash saved: {os.path.relpath(stash_path)}')
        print(f'Working copy reverted to HEAD (commit {commit_id[:12] if len(commit_id) > 12 else commit_id}).')

    def cmd_stash_pop(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        stash     = Vault__Stash(crypto=Vault__Crypto())

        try:
            result = stash.pop(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if result.get('no_stash'):
            print('No stash found.')
            return

        import os
        zip_path = result.get('stash_path', '')
        meta     = result.get('meta')
        restored = result.get('restored', [])
        deleted  = result.get('deleted',  [])

        print(f'Restoring stash: {os.path.basename(zip_path)}')
        for path in restored:
            print(f'  ~ {path}')
        for path in deleted:
            print(f'  - {path}')
        print('\nStash applied and dropped.')

    def cmd_stash_list(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        stash     = Vault__Stash(crypto=Vault__Crypto())

        try:
            entries = stash.list_stashes(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if not entries:
            print('No stashes found.')
            return

        for i, entry in enumerate(entries):
            import os, datetime
            meta      = entry.get('meta')
            zip_path  = entry.get('zip_path', '')
            ts_ms     = entry.get('timestamp', 0)
            ts_s      = ts_ms // 1000
            dt_str    = datetime.datetime.fromtimestamp(ts_s).strftime('%Y-%m-%d %H:%M:%S')
            files_n   = (len(meta.files_added) + len(meta.files_modified) +
                         len(meta.files_deleted)) if meta else '?'
            print(f'stash@{{{i}}}: {os.path.basename(zip_path)}  ({dt_str}, {files_n} files)')

    def cmd_stash_drop(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        stash     = Vault__Stash(crypto=Vault__Crypto())

        try:
            result = stash.drop(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        if result.get('no_stash'):
            print('No stash found.')
            return

        import os
        dropped = result.get('dropped_path', '')
        print(f'Dropped stash: {os.path.basename(dropped)}')
