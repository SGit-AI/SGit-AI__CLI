import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Signature_Reason(Safe_Str):
    """Why a user signature got its status ("key not valid at the commit time …")."""
    regex           = re.compile(r'[\x00-\x1f\x7f]')
    max_length      = 300
    allow_empty     = True
    trim_whitespace = True
