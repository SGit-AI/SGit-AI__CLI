import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# git-like: letters, digits, '.', '_', '-', '/'; starts with a letter or digit; no '..',
# no '//', no trailing '/' or '.'; never looks like an object id, a short id (4+ hex) or
# HEAD (so `history reset <x>` can never mistake one for the other). \Z, not $: '$'
# also matches before a trailing newline, so 'v1.0\n' passed as a new name and moved
# v1.0 without --force (review S8).
TAG_NAME__REGEX      = re.compile(r'^(?!obj-cas-imm-)(?![0-9a-f]{4,}\Z)(?!(?i:head)\Z)(?!.*\.\.)(?!.*//)'
                                  r'[A-Za-z0-9][A-Za-z0-9._/\-]{0,99}(?<![/.])\Z')
TAG_NAME__MAX_LENGTH = 100


class Safe_Str__Tag_Name(Safe_Str):
    regex             = TAG_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = TAG_NAME__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
