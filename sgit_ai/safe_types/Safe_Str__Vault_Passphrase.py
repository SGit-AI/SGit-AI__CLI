import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

VAULT_PASSPHRASE__REGEX      = re.compile(r'^[\x20-\x7E]{1,256}$')
VAULT_PASSPHRASE__MAX_LENGTH = 256

class Safe_Str__Vault_Passphrase(Safe_Str):
    regex             = VAULT_PASSPHRASE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = VAULT_PASSPHRASE__MAX_LENGTH
    allow_empty       = False
    trim_whitespace   = False
    strict_validation = True
