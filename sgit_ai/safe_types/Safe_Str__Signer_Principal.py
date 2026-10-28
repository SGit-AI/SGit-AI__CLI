import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Signer_Principal(Safe_Str):
    """Who a user signature belongs to, from the verifier's own allowed-signers file or
    keyring (never from the vault). Control characters replaced: it is printed."""
    regex           = re.compile(r'[\x00-\x1f\x7f]')
    max_length      = 256
    allow_empty     = True
    trim_whitespace = True
