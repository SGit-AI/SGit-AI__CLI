import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# One branch-index entry this sgit cannot read, kept as its exact JSON text (canonical:
# sorted keys, ASCII escapes) so it is written back unchanged (review eed8084 B1).
INDEX_ENTRY_JSON__REGEX      = re.compile(r'^[\x20-\x7E]*\Z')
INDEX_ENTRY_JSON__MAX_LENGTH = 1024 * 1024


class Safe_Str__Index_Entry_Json(Safe_Str):
    regex             = INDEX_ENTRY_JSON__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = INDEX_ENTRY_JSON__MAX_LENGTH
    allow_empty       = False
    trim_whitespace   = False
    strict_validation = True
