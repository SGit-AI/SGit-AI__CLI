from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Index_Id                    import Safe_Str__Index_Id
from sgit_ai.schemas.Schema__Branch_Meta                      import Schema__Branch_Meta


class Schema__Branch_Index(Type_Safe):
    schema     : Safe_Str__Schema_Version = None          # e.g. 'branch_index_v1'
    branches   : list[Schema__Branch_Meta]
