import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

ENCRYPTED_MESSAGE__REGEX      = re.compile(r'^[A-Za-z0-9+/=]+$')
ENCRYPTED_MESSAGE__MAX_LENGTH = 1_398_140             # base64 of AES-GCM over 1 MiB: what a commit READ accepts


class Safe_Str__Encrypted_Message(Safe_Str):
    """A commit's encrypted message (base64 of 12-byte IV + ciphertext + 16-byte tag).

    Its own type, not Safe_Str__Encrypted_Value (1,024 characters, kept for the tree
    entry fields): that cap meant 740 bytes of message, and any client that wrote more
    made the commit unreadable to this CLI. Reading accepts up to 1 MiB, so a longer
    message from another client never breaks a history walk; writing is capped by
    Vault__Commit_Message (740 bytes, or 64 KiB on a vault with `long-messages`)."""
    regex             = ENCRYPTED_MESSAGE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = ENCRYPTED_MESSAGE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True
