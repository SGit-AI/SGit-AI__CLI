from enum import Enum


class Enum__User_Signature_Format(str, Enum):
    """The kind of key behind a commit's or tag's `user_signature` (Git's gpg.format)."""
    SSH     = 'ssh'
    OPENPGP = 'openpgp'
