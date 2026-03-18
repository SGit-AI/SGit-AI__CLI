import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode
from osbot_utils.type_safe.primitives.domains.identifiers.safe_str.Safe_Str__Id import Safe_Str__Id

# todo: review since this regex was causing too many side effects
# VAULT_ID__REGEX      = re.compile(r'^[a-z0-9]{8}$')
# VAULT_ID__MAX_LENGTH = 8
#
# class Safe_Str__Vault_Id(Safe_Str):
#     regex             = VAULT_ID__REGEX
#     regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
#     max_length        = VAULT_ID__MAX_LENGTH
#     exact_length      = True
#     allow_empty       = True
#     trim_whitespace   = True
#     to_lower_case     = True
#     strict_validation = True

class Safe_Str__Vault_Id(Safe_Str__Id):
    to_lower_case     = True