import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# a pack's file name: <epoch:10>__<commit id>__<bytes>.zip (Vault__Packs.PACK_NAME_RE)
PACK_NAME__REGEX      = re.compile(r'^\d{10}__obj-cas-imm-[0-9a-f]{12,32}__\d+\.zip$')
PACK_NAME__MAX_LENGTH = 96

class Safe_Str__Pack_Name(Safe_Str):
    regex             = PACK_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = PACK_NAME__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
