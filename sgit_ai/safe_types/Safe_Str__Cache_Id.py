import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# cch-pid-{snw|muw}-{12 hex}  — cache-layer id (contract 08/12 v0, D3).
# The snw|muw label is an output label, not hashed; the 12-hex tail is
# HMAC-SHA256(read_key, cache domain)[:12]. Distinct family from obj-cas-imm-*,
# ref-pid-*, idx-pid-*, key-rnd-imm-*.
CACHE_ID__REGEX      = re.compile(r'^cch-pid-(snw|muw)-[0-9a-f]{12}$')
CACHE_ID__MAX_LENGTH = 24

class Safe_Str__Cache_Id(Safe_Str):
    regex             = CACHE_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = CACHE_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True
