import time

from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.safe_types.Safe_Str__Object_Id  import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_UInt__Timestamp import Safe_UInt__Timestamp


class Schema__Stash_Meta(Type_Safe):
    created_at     : Safe_UInt__Timestamp  # milliseconds since epoch
    base_commit    : Safe_Str__Object_Id   = None
    files_added    : list                  # list of str paths
    files_modified : list                  # list of str paths
    files_deleted  : list                  # list of str paths

    def setup(self):
        if not int(self.created_at):
            self.created_at = Safe_UInt__Timestamp(int(time.time() * 1000))
        return self
