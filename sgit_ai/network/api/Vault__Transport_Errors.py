"""Transport-level errors for the static/folder read path.

Defined in the network layer because the static transport raises them and the
layering rule forbids network → core imports; core/Vault__Errors re-exports
them so every vault error stays findable in one place.
"""

MSG_READ_ONLY_TRANSPORT = (
    'this vault was opened over a static/folder transport, which is read-only: '
    'the host is a plain file server and has no write endpoint. '
    'To push changes, open the vault against the live API '
    '(--transport api with --base-url/--token, or `sgit remote add`).'
)


class Vault__Read_Only_Transport_Error(Exception):
    """Raised when a write reaches a static/folder transport. Writes on a
    static transport must raise — never silently no-op."""

    def __init__(self, message: str = MSG_READ_ONLY_TRANSPORT):
        super().__init__(message)


class Vault__Static_Transport_Error(Exception):
    """Raised when a static host cannot be reached at all (connection refused/
    reset/timeout). Deliberately distinct from an absent object: only an HTTP
    404 means 'absent' — a dead host must never diagnose as an empty vault
    (tabletop 11, F5)."""

    def __init__(self, message: str = 'static host unreachable'):
        super().__init__(message)
