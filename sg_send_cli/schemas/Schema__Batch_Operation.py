from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Enum__Batch_Op                        import Enum__Batch_Op
from sg_send_cli.safe_types.Safe_Str__Base64_Data                 import Safe_Str__Base64_Data
from sg_send_cli.safe_types.Safe_Str__File_Path                   import Safe_Str__File_Path
from sg_send_cli.safe_types.Safe_Str__SHA256                      import Safe_Str__SHA256


class Schema__Batch_Operation(Type_Safe):
    op      : Enum__Batch_Op              = None              # 'write', 'write-if-match', 'delete'
    file_id : Safe_Str__File_Path         = None              # path within vault (e.g. 'bare/data/obj-abc123')
    data    : Safe_Str__Base64_Data       = None              # base64-encoded content for writes
    match   : Safe_Str__SHA256            = None              # expected hash for write-if-match (optional)
