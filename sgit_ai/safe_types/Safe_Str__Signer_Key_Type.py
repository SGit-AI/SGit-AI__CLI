import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Signer_Key_Type(Safe_Str):
    """ED25519, ECDSA, RSA, ED25519-SK, ECDSA-SK, or an OpenPGP algorithm name (display)."""
    regex           = re.compile(r'[^A-Za-z0-9\-_]')
    max_length      = 32
    allow_empty     = True
    trim_whitespace = True
