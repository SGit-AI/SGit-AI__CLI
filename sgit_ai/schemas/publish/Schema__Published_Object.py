from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Safe_Str__Published_File_Id     import Safe_Str__Published_File_Id
from sgit_ai.safe_types.Safe_Str__SHA256                import Safe_Str__SHA256
from sgit_ai.safe_types.Safe_UInt__File_Size            import Safe_UInt__File_Size


class Schema__Published_Object(Type_Safe):
    """One store file in manifest.json's objects[] — custody without access.

    sha256 is the hash of the CIPHERTEXT, so a keyless mirror can verify
    files that are not content-addressed (refs/indexes/keys). For
    obj-cas-imm-* names, consumers recompute the id from the bytes and IGNORE
    this field — the manifest is self-attested by the same host (SP-3).
    """
    file_id : Safe_Str__Published_File_Id = None
    size    : Safe_UInt__File_Size
    sha256  : Safe_Str__SHA256            = None
