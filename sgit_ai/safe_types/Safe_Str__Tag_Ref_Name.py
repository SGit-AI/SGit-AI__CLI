import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# A tag name as STORED (in the branch index and in the signed tag object): the character
# set only. The naming rule (Safe_Str__Tag_Name / TAG_NAME__REGEX) is what `tag create`
# accepts and it changes between versions; reading must not depend on it, or one entry
# valid under another version's rule broke every clone of the vault (review 0a0707d R1).
TAG_REF_NAME__REGEX      = re.compile(r'^[A-Za-z0-9._/\-]{1,100}\Z')
TAG_REF_NAME__MAX_LENGTH = 100


class Safe_Str__Tag_Ref_Name(Safe_Str):
    regex             = TAG_REF_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = TAG_REF_NAME__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True
