import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# A container runtime's name, which is also its CLI binary: docker, podman, nerdctl, finch,
# container (Apple), uv (the no-container engine).
CONTAINER_RUNTIME__REGEX = re.compile(r'^[a-z][a-z0-9\-]{0,31}\Z')


class Safe_Str__Container_Runtime(Safe_Str):
    regex             = CONTAINER_RUNTIME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 32
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
