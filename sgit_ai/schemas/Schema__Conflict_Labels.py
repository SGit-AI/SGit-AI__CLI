from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_Str__Conflict_Label      import Safe_Str__Conflict_Label


class Schema__Conflict_Labels(Type_Safe):
    ours   : Safe_Str__Conflict_Label = 'ours'
    base   : Safe_Str__Conflict_Label = 'base'
    theirs : Safe_Str__Conflict_Label = 'theirs'
