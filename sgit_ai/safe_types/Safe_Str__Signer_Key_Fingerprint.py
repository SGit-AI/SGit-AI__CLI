import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode


class Safe_Str__Signer_Key_Fingerprint(Safe_Str):
    """A user-signing key's fingerprint as its own tools print it: SSH `SHA256:<43 base64>`,
    OpenPGP v4 (40 hex) or v5/v6 (64 hex). (Safe_Str__Key_Fingerprint is the PKI one.)"""
    regex             = re.compile(r'^(SHA256:[A-Za-z0-9+/]{43}|[0-9A-F]{40}|[0-9A-F]{64})$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 64
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
