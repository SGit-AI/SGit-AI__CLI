from osbot_utils.type_safe.Type_Safe                        import Type_Safe
from sgit_ai.safe_types.Safe_Str__Schema_Version        import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__File_Path             import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Content_Type          import Safe_Str__Content_Type
from sgit_ai.safe_types.Safe_Str__Content_Hash          import Safe_Str__Content_Hash
from sgit_ai.safe_types.Safe_Str__Base64_Data           import Safe_Str__Base64_Data
from sgit_ai.safe_types.Safe_UInt__File_Size            import Safe_UInt__File_Size
from sgit_ai.safe_types.Enum__Cache_Kind                import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability          import Enum__Cache_Mutability


class Schema__Cache_Value(Type_Safe):
    """Plaintext of a value cache object — a copy of a file's content at a
    client-computable, path-derived location. Contract 08/12 v0 §6.1.

    Encrypted with a RANDOM IV (crypto.encrypt) and written directly to
    bare/cache/value/{cache_file_id}; never via the object store (D10).
    """
    schema       : Safe_Str__Schema_Version = None       # MUST equal 'cache_value_v1'
    kind         : Enum__Cache_Kind         = Enum__Cache_Kind.VALUE
    path         : Safe_Str__File_Path      = None        # collision guard (reader verifies vs derived id)
    mutability   : Enum__Cache_Mutability   = Enum__Cache_Mutability.SNW
    commit_id    : Safe_Str__Object_Id      = None        # named-branch commit reflected — staleness marker
    content_type : Safe_Str__Content_Type   = None
    size         : Safe_UInt__File_Size                   # plaintext byte length
    content_hash : Safe_Str__Content_Hash   = None        # sha256(plaintext)[:12], as flatten() reports
    value_b64    : Safe_Str__Base64_Data    = None        # base64 of the file's plaintext content
