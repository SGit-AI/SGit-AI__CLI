import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode


class Safe_Str__Content_Path(Safe_Str):
    """A vault content path for output (JSON rows of diff, blame, grep): any printable
    Unicode (`josé.md` stays `josé.md`, which Safe_Str__File_Path would rewrite), no
    control character. A decrypted name holding one is refused, never rewritten:
    plain output quotes it with Vault__Path_Quote instead."""
    regex             = re.compile(r'^[^\x00-\x1f\x7f]*$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 4096
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True
