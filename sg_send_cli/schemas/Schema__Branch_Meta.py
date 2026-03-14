from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Branch_Id                   import Safe_Str__Branch_Id
from sg_send_cli.safe_types.Safe_Str__Branch_Name                 import Safe_Str__Branch_Name
from sg_send_cli.safe_types.Safe_Str__Ref_Id                      import Safe_Str__Ref_Id
from sg_send_cli.safe_types.Safe_Str__Key_Id                      import Safe_Str__Key_Id
from sg_send_cli.safe_types.Safe_UInt__Timestamp                  import Safe_UInt__Timestamp
from sg_send_cli.safe_types.Enum__Branch_Type                     import Enum__Branch_Type


class Schema__Branch_Meta(Type_Safe):
    branch_id      : Safe_Str__Branch_Id   = None
    name           : Safe_Str__Branch_Name = None
    branch_type    : Enum__Branch_Type     = Enum__Branch_Type.NAMED
    head_ref_id    : Safe_Str__Ref_Id      = None
    public_key_id  : Safe_Str__Key_Id      = None
    private_key_id : Safe_Str__Key_Id      = None          # None for clone branches (private key stored locally)
    created_at     : Safe_UInt__Timestamp
    creator_branch : Safe_Str__Branch_Id   = None          # branch that created this branch (None for initial)
