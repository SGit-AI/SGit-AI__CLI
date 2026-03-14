from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sg_send_cli.safe_types.Safe_Str__Content_Hash            import Safe_Str__Content_Hash
from sg_send_cli.safe_types.Safe_UInt__File_Size              import Safe_UInt__File_Size


class Schema__Object_Tree_Entry(Type_Safe):
    path         : Safe_Str__File_Path    = None          # legacy flat path (kept for backward compat)
    name         : Safe_Str__File_Path    = None          # v2: filename within this directory level
    blob_id      : Safe_Str__Object_Id    = None          # object ID of blob (None for directories)
    tree_id      : Safe_Str__Object_Id    = None          # v2: object ID of sub-tree (None for files)
    size         : Safe_UInt__File_Size                    # legacy/v2: file size
    content_hash : Safe_Str__Content_Hash = None          # v2: SHA256(plaintext)[:12]
