from enum import Enum


class Enum__Key_Kind(Enum):
    """What a credential string declares itself to be.

    The declaration lives in the prefix, so classification never guesses from
    shape — the mistake that misrouted a 64-hex passphrase before prefixes
    existed. UNKNOWN covers legacy bare keys, which callers resolve by context.
    """
    VAULT        = 'vault'          # full capability: read AND write
    READ_PRIVATE = 'read-private'   # read-only, NOT meant to be published
    READ_PUBLIC  = 'read-public'    # read-only, deliberately published
    UNKNOWN      = 'unknown'        # unprefixed / legacy / not a key
