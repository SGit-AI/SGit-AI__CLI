import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

VAULT_PATH__REGEX      = re.compile(r'[^a-zA-Z0-9/\\_.\- ]')
VAULT_PATH__MAX_LENGTH = 4096

class Safe_Str__Vault_Path(Safe_Str):
    regex       = VAULT_PATH__REGEX
    max_length  = VAULT_PATH__MAX_LENGTH
    allow_empty = True
