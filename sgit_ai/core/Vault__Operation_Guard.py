"""Vault__Operation_Guard — one rule for "an operation is in progress".

A merge with conflicts (and, as they land, a bisect or a rebase) leaves state under
this clone's `.sg_vault/local/`. While it is there, commands that would change what
the operation is working on are refused by name, with the way to finish or abandon
it (design__00 F5, table 2.1). Every command reads the same files, so a worktree's
operation never blocks another worktree: the state is per clone.
"""
import os
from   osbot_utils.type_safe.Type_Safe import Type_Safe

MERGE_STATE_FILE  = 'merge_state.json'
BISECT_STATE_FILE = 'bisect.json'                              # design__05
REBASE_STATE_FILE = os.path.join('rebase', 'state.json')       # design__07

OPERATIONS = (('merge' , MERGE_STATE_FILE , "Use 'sgit resolve' to resolve conflicts, then 'sgit commit'. "
                                            "Or 'sgit merge-abort' to discard the merge."),
              ('bisect', BISECT_STATE_FILE, "Finish it with 'sgit history bisect reset'."),
              ('rebase', REBASE_STATE_FILE, "Finish it with 'sgit history rebase --continue', "
                                            "or 'sgit history rebase --abort'."))


class Vault__Operation_Guard(Type_Safe):

    def in_progress(self, directory: str) -> str:
        """The operation under way in this clone ('merge', 'bisect', 'rebase'), or ''."""
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        local_dir = Vault__Storage().local_dir(directory)
        for name, state_file, _ in OPERATIONS:
            if os.path.isfile(os.path.join(local_dir, state_file)):
                return name
        return ''

    def check(self, directory: str, action: str) -> None:
        from sgit_ai.core.Vault__Errors import Vault__Merge_In_Progress_Error, Vault__Operation_In_Progress_Error
        operation = self.in_progress(directory)
        if not operation:
            return
        hint = dict((name, text) for name, _, text in OPERATIONS)[operation]
        message = f'Cannot {action}: {operation} in progress. {hint}'
        if operation == 'merge':
            raise Vault__Merge_In_Progress_Error(message)
        raise Vault__Operation_In_Progress_Error(message)
