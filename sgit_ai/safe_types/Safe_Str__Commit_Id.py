import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# Commit object ID: obj-cas-imm-{12hex} — must allow dashes
class Safe_Str__Commit_Id(Safe_Str):
    regex             = re.compile(r'[^a-zA-Z0-9\-]')
    max_length        = 128
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = False
