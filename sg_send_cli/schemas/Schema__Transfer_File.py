from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Transfer_Id             import Safe_Str__Transfer_Id
from sg_send_cli.safe_types.Safe_Str__SHA256                  import Safe_Str__SHA256
from sg_send_cli.safe_types.Safe_Str__Content_Type            import Safe_Str__Content_Type
from sg_send_cli.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sg_send_cli.safe_types.Safe_UInt__File_Size              import Safe_UInt__File_Size


class Schema__Transfer_File(Type_Safe):
    transfer_id   : Safe_Str__Transfer_Id  = None
    file_path     : Safe_Str__File_Path    = None
    file_hash     : Safe_Str__SHA256       = None
    file_size     : Safe_UInt__File_Size
    content_type  : Safe_Str__Content_Type = None
