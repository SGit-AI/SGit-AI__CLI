# Typed exceptions for vault sync operations.
# Message constants keep raise sites grep-able without raw strings.

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
