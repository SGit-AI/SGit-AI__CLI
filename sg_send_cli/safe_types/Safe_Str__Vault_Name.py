import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

VAULT_NAME__REGEX      = re.compile(r'[^a-zA-Z0-9 _\-.]')
VAULT_NAME__MAX_LENGTH = 128

class Safe_Str__Vault_Name(Safe_Str):
    regex       = VAULT_NAME__REGEX
    max_length  = VAULT_NAME__MAX_LENGTH
    allow_empty = True
