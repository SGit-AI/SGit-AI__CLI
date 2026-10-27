import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# a logical member name inside an index pack: flat, changes, commit-gen, folder:<path>,
# commits:<n>, blob-paths:<xx>, file-commits:<xx>; the path part may hold any character
# a vault path may (it is inside the encrypted header, never a zip member name)
INDEX_MEMBER_NAME__REGEX      = re.compile(r'^[a-z][a-z-]*(?::[^\x00-\x1f]*)?$')
INDEX_MEMBER_NAME__MAX_LENGTH = 4200

class Safe_Str__Index_Member_Name(Safe_Str):
    regex             = INDEX_MEMBER_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = INDEX_MEMBER_NAME__MAX_LENGTH
    allow_empty       = False
    trim_whitespace   = False
    strict_validation = True
