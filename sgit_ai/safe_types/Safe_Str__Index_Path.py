import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# a vault-relative path as an index member records it: '/'-separated, no leading slash,
# '' for the root folder; no control characters. Not a path guard (that is
# Vault__Path_Guard, applied before any write): a value, inside an encrypted member.
INDEX_PATH__REGEX      = re.compile(r'^(?!/)[^\x00-\x1f]*$')
INDEX_PATH__MAX_LENGTH = 4096

class Safe_Str__Index_Path(Safe_Str):
    regex             = INDEX_PATH__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = INDEX_PATH__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True
