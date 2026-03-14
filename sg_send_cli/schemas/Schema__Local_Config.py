from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Branch_Id                   import Safe_Str__Branch_Id


class Schema__Local_Config(Type_Safe):
    my_branch_id : Safe_Str__Branch_Id = None              # the clone branch ID for this local checkout
