from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Enum__Line_Merge_Outcome      import Enum__Line_Merge_Outcome
from sgit_ai.safe_types.Safe_Str__Merge_Reason        import Safe_Str__Merge_Reason
from sgit_ai.safe_types.Safe_UInt__Hunk_Count         import Safe_UInt__Hunk_Count


class Schema__Line_Merge_Result(Type_Safe):
    outcome : Enum__Line_Merge_Outcome = None
    hunks   : Safe_UInt__Hunk_Count                  # conflict blocks written (git merge-file's exit code)
    reason  : Safe_Str__Merge_Reason   = None
