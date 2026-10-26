from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt        import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Index_Member_Name        import Safe_Str__Index_Member_Name
from sgit_ai.safe_types.Safe_Str__Sha256_Hex               import Safe_Str__Sha256_Hex


class Schema__Pack_Index__Member(Type_Safe):
    """One row of the header's member table: where a logical member sits in the zip
    (the offset of its bytes, past the local file header) and the sha256 of its
    plaintext JSON, so a reader checks a member on first read without the central
    directory."""
    name   : Safe_Str__Index_Member_Name = None
    seq    : Safe_UInt                               # the zip member index/<seq:06d>
    offset : Safe_UInt                               # byte offset of the member's data in the zip
    length : Safe_UInt                               # bytes of the (encrypted, deflated) member
    sha256 : Safe_Str__Sha256_Hex        = None      # of the plaintext JSON
