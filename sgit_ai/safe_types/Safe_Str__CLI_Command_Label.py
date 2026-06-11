import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

CLI_COMMAND_LABEL__REGEX      = re.compile(r'^[a-zA-Z0-9 _\-]{1,80}$')
CLI_COMMAND_LABEL__MAX_LENGTH = 80


class Safe_Str__CLI_Command_Label(Safe_Str):
    regex             = CLI_COMMAND_LABEL__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = CLI_COMMAND_LABEL__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
