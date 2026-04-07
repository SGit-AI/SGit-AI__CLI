import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

#VAULT_KEY__REGEX      = re.compile(r'^[\x20-\x7E]+:[a-z0-9]{8}$')
# Accepts both passphrase:vault_id format AND simple token format (word-word-NNNN)
VAULT_KEY__REGEX      = re.compile(r'^([\x20-\x7E]+:[a-z0-9]|[a-z]+-[a-z]+-\d{4})')
VAULT_KEY__MAX_LENGTH = 268

class Safe_Str__Vault_Key(Safe_Str):
    regex             = VAULT_KEY__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = VAULT_KEY__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
