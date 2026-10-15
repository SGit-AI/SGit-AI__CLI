import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# An OCI image reference or digest: registry/repo:tag, repo@sha256:…; never a flag (no leading '-').
IMAGE_REF__REGEX = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.:/@\-]{0,299}\Z')


class Safe_Str__Image_Ref(Safe_Str):
    regex             = IMAGE_REF__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 300
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
