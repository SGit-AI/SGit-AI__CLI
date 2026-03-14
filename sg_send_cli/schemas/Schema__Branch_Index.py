from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sg_send_cli.safe_types.Safe_Str__Index_Id                    import Safe_Str__Index_Id
from sg_send_cli.schemas.Schema__Branch_Meta                      import Schema__Branch_Meta


class Schema__Branch_Index(Type_Safe):
    schema     : Safe_Str__Schema_Version = None          # e.g. 'branch_index_v1'
    index_id   : Safe_Str__Index_Id       = None
    branches   : list[Schema__Branch_Meta]
