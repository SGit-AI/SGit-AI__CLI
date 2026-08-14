from osbot_utils.type_safe.Type_Safe                        import Type_Safe
from sgit_ai.safe_types.Safe_Str__Schema_Version        import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Cache_Path            import Safe_Str__Cache_Path
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Content_Type          import Safe_Str__Content_Type
from sgit_ai.safe_types.Safe_Str__Content_Hash          import Safe_Str__Content_Hash
from sgit_ai.safe_types.Safe_UInt__File_Size            import Safe_UInt__File_Size
from sgit_ai.safe_types.Enum__Cache_Kind                import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability          import Enum__Cache_Mutability
from sgit_ai.safe_types.Enum__Cache_Target_Kind         import Enum__Cache_Target_Kind


class Schema__Cache_Pointer(Type_Safe):
    """Plaintext of a pointer cache object — a path-derived locator holding a
    blob_id (file) or tree_id (folder/subtree). Contract 08/12 v0 §6.2.

    Encrypted with a RANDOM IV (crypto.encrypt) and written directly to
    bare/cache/pointer/{cache_file_id}; never via the object store (D10).
    """
    schema       : Safe_Str__Schema_Version   = None     # MUST equal 'cache_pointer_v1'
    kind         : Enum__Cache_Kind           = Enum__Cache_Kind.POINTER
    path         : Safe_Str__Cache_Path       = None      # collision guard
    mutability   : Enum__Cache_Mutability     = Enum__Cache_Mutability.SNW
    commit_id    : Safe_Str__Object_Id        = None      # staleness marker
    content_type : Safe_Str__Content_Type     = None
    size         : Safe_UInt__File_Size                   # plaintext byte length (0 for a tree)
    target_kind  : Enum__Cache_Target_Kind    = Enum__Cache_Target_Kind.BLOB
    target_id    : Safe_Str__Object_Id        = None      # blob_id (file) or tree_id (folder)
    content_hash : Safe_Str__Content_Hash     = None      # present when target_kind == blob
