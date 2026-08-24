from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sgit_ai.safe_types.Enum__Local_Config_Mode               import Enum__Local_Config_Mode
from sgit_ai.safe_types.Enum__Visibility                      import Enum__Visibility
from sgit_ai.safe_types.Safe_Str__Branch_Id                   import Safe_Str__Branch_Id


class Schema__Local_Config(Type_Safe):
    my_branch_id       : Safe_Str__Branch_Id       = None
    mode               : Enum__Local_Config_Mode   = None
    sparse             : bool                      = False
    # Publishing visibility is PER CLONE, never vault content (decision 5): a
    # clone must not inherit somebody else's publishing settings, and a fresh
    # clone defaults to bare. None = never published from this clone.
    publish_visibility : Enum__Visibility          = None
