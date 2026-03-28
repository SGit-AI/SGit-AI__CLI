from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.safe_types.Safe_Str__Branch_Id  import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Object_Id  import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__SHA256     import Safe_Str__SHA256


class Schema__Archive_Provenance(Type_Safe):
    branch_id  : Safe_Str__Branch_Id = None   # clone-branch or named-branch ID
    commit_id  : Safe_Str__Object_Id = None   # HEAD commit at time of archive
    author_key : Safe_Str__SHA256    = None   # key fingerprint, or None
