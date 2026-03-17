from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Object_Id               import Safe_Str__Object_Id
from sg_send_cli.safe_types.Safe_Str__Encrypted_Value         import Safe_Str__Encrypted_Value


class Schema__Object_Tree_Entry(Type_Safe):
    blob_id          : Safe_Str__Object_Id       = None   # file → obj-cas-imm-{hash}
    tree_id          : Safe_Str__Object_Id       = None   # folder → obj-cas-imm-{hash}
    name_enc         : Safe_Str__Encrypted_Value = None   # AES-GCM encrypted filename (base64)
    size_enc         : Safe_Str__Encrypted_Value = None   # AES-GCM encrypted file size (base64)
    content_hash_enc : Safe_Str__Encrypted_Value = None   # AES-GCM encrypted content hash (base64)
