import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

CONTAINER_NAME__REGEX = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')     # what docker, podman and container accept


class Safe_Str__Container_Name(Safe_Str):
    regex             = CONTAINER_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 128
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
