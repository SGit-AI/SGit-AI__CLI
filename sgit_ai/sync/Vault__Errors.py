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
    """Raised when write_file is called on a read-only vault clone.

    A vault is read-only when it was cloned without the full vault
    passphrase (i.e. only a read_key was stored in clone_mode.json).
    The write_key is absent from Vault__Components in that case.
    """

    def __init__(self, message: str = MSG_WRITE_KEY_MISSING):
        super().__init__(message)


class Vault__Clone_Mode_Corrupt_Error(Exception):
    """Raised when clone_mode.json exists but cannot be parsed or is
    missing mandatory fields (mode, read_key, vault_id).

    Fail-closed: rather than silently treating the vault as full-mode
    (which would allow writes on what may be a read-only clone), we
    raise and require the operator to fix or re-clone the vault.
    """

    def __init__(self, message: str = MSG_CLONE_MODE_CORRUPT):
        super().__init__(message)
