import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode


class Safe_Str__User_Signature_Blob(Safe_Str):
    """Base64 of a binary user signature: an SSHSIG blob (not armored) or an OpenPGP
    signature packet. 8 KiB holds an RSA-8192 SSHSIG (about 2.9 KB of base64)."""
    regex             = re.compile(r'^[A-Za-z0-9+/]{16,8188}={0,2}$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 8192
    allow_empty       = False
    trim_whitespace   = True
    strict_validation = True
