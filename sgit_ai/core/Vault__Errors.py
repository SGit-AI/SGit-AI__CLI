"""Typed exceptions for vault sync operations.

All exception messages use a fixed string constant rather than a raw
string at the raise site, so call-sites are checkable and grep-able.
"""

MSG_WRITE_KEY_MISSING = (
    'vault is read-only: write_key is absent. '
    'This vault was cloned in read-only mode. '
    'Use a full clone (with vault passphrase) to write files.'
)

MSG_CLONE_MODE_CORRUPT = (
    'clone_mode.json is malformed or missing required fields. '
    'The vault will not open in order to prevent a silently-demoted '
    'read-only clone from accepting writes.'
)


class Vault__Read_Only_Error(Exception):
    """Raised when write_file is called on a read-only vault clone."""

    def __init__(self, message: str = MSG_WRITE_KEY_MISSING):
        super().__init__(message)


class Vault__Clone_Mode_Corrupt_Error(Exception):
    """Raised when clone_mode.json is missing or cannot be parsed. Fail-closed."""

    def __init__(self, message: str = MSG_CLONE_MODE_CORRUPT):
        super().__init__(message)


class Vault__Merge_In_Progress_Error(Exception):
    def __init__(self, message: str = 'merge in progress'):
        super().__init__(message)


class Vault__Push_With_Conflicts_Error(Exception):
    def __init__(self, message: str = 'unresolved .conflict files in working tree'):
        super().__init__(message)


class Vault__Push_Non_Fast_Forward_Error(Exception):
    def __init__(self, message: str = 'remote has diverged; run sgit pull to merge first'):
        super().__init__(message)


# Static-transport errors are defined in the network layer (the transport
# raises them, and network must not import core); re-exported here so callers
# find every vault error in one place.
from sgit_ai.network.api.Vault__Transport_Errors import (               # noqa: F401,E402
    MSG_READ_ONLY_TRANSPORT,
    Vault__Read_Only_Transport_Error,
    Vault__Static_Transport_Error,
)
