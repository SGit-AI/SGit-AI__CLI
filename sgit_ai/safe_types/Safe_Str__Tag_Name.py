import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# git-like: letters, digits, '.', '_', '-', '/'; starts with a letter or digit; no '..',
# no '//', no trailing '/' or '.'; never looks like an object id (so `history reset <x>`
# can tell a tag from an id).
TAG_NAME__REGEX      = re.compile(r'^(?!obj-cas-imm-)(?!.*\.\.)(?!.*//)[A-Za-z0-9][A-Za-z0-9._/\-]{0,99}(?<![/.])$')
TAG_NAME__MAX_LENGTH = 100


class Safe_Str__Tag_Name(Safe_Str):
    regex             = TAG_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = TAG_NAME__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
