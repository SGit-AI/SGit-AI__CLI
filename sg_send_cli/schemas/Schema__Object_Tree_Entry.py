from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sg_send_cli.safe_types.Safe_UInt__File_Size              import Safe_UInt__File_Size


class Schema__Object_Tree_Entry(Type_Safe):
    path    : Safe_Str__File_Path   = None
    blob_id : Safe_Str__Object_Id   = None
    size    : Safe_UInt__File_Size
