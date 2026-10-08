from osbot_utils.type_safe.Type_Safe                     import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt     import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Ref_Id                 import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id              import Safe_Str__Commit_Id


class Schema__Reflog_Entry(Type_Safe):
    timestamp_ms : Safe_UInt                               # when the ref moved (local clock)
    ref_id       : Safe_Str__Ref_Id    = None              # which ref (the clone branch's head, the named ref, ...)
    old_commit   : Safe_Str__Commit_Id = None              # None: the ref did not exist yet
    new_commit   : Safe_Str__Commit_Id = None
