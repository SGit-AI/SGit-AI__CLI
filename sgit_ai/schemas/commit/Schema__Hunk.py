from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.safe_types.Safe_Str__Diff_Header      import Safe_Str__Diff_Header
from sgit_ai.safe_types.Safe_Str__Diff_Text        import Safe_Str__Diff_Text
from sgit_ai.safe_types.Safe_Str__Hunk_Id          import Safe_Str__Hunk_Id
from sgit_ai.safe_types.Safe_UInt__Hunk_Count      import Safe_UInt__Hunk_Count
from sgit_ai.safe_types.Safe_UInt__Line_Number     import Safe_UInt__Line_Number
from sgit_ai.schemas.Schema__Line_Hunk             import Schema__Line_Hunk


class Schema__Hunk(Type_Safe):
    """One hunk of `sgit commit --list-hunks`: what Git's `add -p` shows as one hunk.
    `changes` are the differ's change blocks inside it (more than one: splittable);
    applying a hunk takes the work side of each. Line numbers are 1-based as in a
    unified header; `text` is the hunk body for display."""
    hunk_id    : Safe_Str__Hunk_Id
    index      : Safe_UInt__Hunk_Count
    old_start  : Safe_UInt__Line_Number
    old_lines  : Safe_UInt__Line_Number
    new_start  : Safe_UInt__Line_Number
    new_lines  : Safe_UInt__Line_Number
    added      : Safe_UInt__Line_Number
    removed    : Safe_UInt__Line_Number
    header     : Safe_Str__Diff_Header
    text       : Safe_Str__Diff_Text
    splittable : bool = False
    whole_file : bool = False
    changes    : list[Schema__Line_Hunk]
