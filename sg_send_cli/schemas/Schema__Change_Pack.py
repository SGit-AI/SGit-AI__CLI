from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sg_send_cli.safe_types.Safe_Str__Branch_Id                   import Safe_Str__Branch_Id
from sg_send_cli.safe_types.Safe_Str__Key_Id                      import Safe_Str__Key_Id
from sg_send_cli.safe_types.Safe_Str__Signature                   import Safe_Str__Signature
from sg_send_cli.safe_types.Safe_Str__SHA256                      import Safe_Str__SHA256
from sg_send_cli.safe_types.Safe_UInt__Timestamp                  import Safe_UInt__Timestamp


class Schema__Change_Pack(Type_Safe):
    schema       : Safe_Str__Schema_Version = None          # e.g. 'change_pack_v1'
    branch_id    : Safe_Str__Branch_Id      = None
    created_at   : Safe_UInt__Timestamp
    creator_key  : Safe_Str__Key_Id         = None
    signature    : Safe_Str__Signature      = None
    payload_hash : Safe_Str__SHA256         = None
    payload      : list[str]                                # list of file IDs included in this change pack
