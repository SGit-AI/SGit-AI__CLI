import sys

from osbot_utils.type_safe.Type_Safe   import Type_Safe
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Branch_Switch import Vault__Branch_Switch


class CLI__Branch(Type_Safe):

    def cmd_branch_new(self, args):
        """sgit branch new <name> [directory] [--from <branch-id>]"""
        directory   = getattr(args, 'directory', '.') or '.'
        name        = getattr(args, 'name', None)
        from_branch = getattr(args, 'from_branch', None)

        if not name:
            print('error: branch name is required', file=sys.stderr)
            sys.exit(1)

        switcher = Vault__Branch_Switch(crypto=Vault__Crypto())

        try:
            result = switcher.branch_new(directory, name, from_branch_id=from_branch)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        named_id = result['named_branch_id']
        clone_id = result['clone_branch_id']

        print(f'Creating named branch: {name}')
        print(f'  Branch ID: {named_id}')
        print(f'  Clone:     {clone_id}')
        print()
        print(f"Switched to new branch '{name}'.")

    def cmd_branch_list(self, args):
        """sgit branch list [directory]"""
        directory = getattr(args, 'directory', '.') or '.'
        switcher  = Vault__Branch_Switch(crypto=Vault__Crypto())

        try:
            result = switcher.branch_list(directory)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        branches     = result['branches']
        my_branch_id = result['my_branch_id']

        if not branches:
            print('No branches found.')
            return

        print('Branches:')

        # Find which named branch the current clone tracks
        clone_to_named = {}
        id_to_branch   = {b['branch_id']: b for b in branches}
        for b in branches:
            if b['branch_type'] == 'clone' and b['creator_branch']:
                clone_to_named[b['branch_id']] = b['creator_branch']

        current_named_id = clone_to_named.get(my_branch_id, '')

        for b in branches:
            if b['branch_type'] != 'named':
                continue
            bid     = b['branch_id']
            bname   = b['name']
            is_curr = bid == current_named_id

            # Find clone branch currently tracking this named branch
            current_clone = ''
            if is_curr:
                current_clone = my_branch_id

            marker = '*' if is_curr else ' '
            line   = f'  {marker} {bname:<20} {bid}'
            if is_curr and current_clone:
                line += f'  (current via {current_clone})'
            print(line)

    def cmd_switch(self, args):
        """sgit switch <name-or-id> [directory]"""
        directory  = getattr(args, 'directory', '.') or '.'
        name_or_id = getattr(args, 'name_or_id', None)

        if not name_or_id:
            print('error: branch name or ID is required', file=sys.stderr)
            sys.exit(1)

        switcher = Vault__Branch_Switch(crypto=Vault__Crypto())

        try:
            result = switcher.switch(directory, name_or_id)
        except FileNotFoundError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            msg = str(e)
            if 'uncommitted changes' in msg:
                print(f'Error: {msg}', file=sys.stderr)
            else:
                print(f'error: {msg}', file=sys.stderr)
            sys.exit(1)

        named_name   = result['named_name']
        named_id     = result['named_branch_id']
        new_clone_id = result['new_clone_branch_id']
        old_clone_id = result['old_clone_branch_id']
        files        = result['files_restored']
        reused       = result.get('reused', False)

        print(f'Switching to named branch: {named_name} ({named_id})')
        if reused:
            print(f'  Found existing clone branch: {new_clone_id} (resuming)')
        else:
            print(f'  No local clone branch found — creating new clone branch...')
            print(f'  New clone: {new_clone_id}')
        print(f'  Checking out files... {files} file(s)')
        print()
        if reused:
            print(f"Resumed branch '{named_name}' via existing clone {new_clone_id}.")
        else:
            print(f"Switched to branch '{named_name}' via new clone branch {new_clone_id}.")
            print(f'  Previous clone: {old_clone_id} (preserved in vault history)')
