from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__SHA256                  import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_Str__Transfer_Id             import Safe_Str__Transfer_Id
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_UInt__File_Size              import Safe_UInt__File_Size
from sgit_ai.safe_types.Enum__Sync_State                  import Enum__Sync_State


class Schema__Vault_Index_Entry(Type_Safe):
    file_path          : Safe_Str__File_Path    = None
    local_hash         : Safe_Str__SHA256       = None
    local_size         : Safe_UInt__File_Size
    remote_transfer_id : Safe_Str__Transfer_Id  = None
    remote_hash        : Safe_Str__SHA256       = None
    remote_size        : Safe_UInt__File_Size
    state              : Enum__Sync_State       = Enum__Sync_State.SYNCED
