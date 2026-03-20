from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Safe_Str__Secret_Key          import Safe_Str__Secret_Key
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp       import Safe_Str__ISO_Timestamp


class Schema__Secret_Entry(Type_Safe):
    key        : Safe_Str__Secret_Key    = None
    created_at : Safe_Str__ISO_Timestamp = None
