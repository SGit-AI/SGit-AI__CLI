"""Errors for partial (scoped / shallow) clones. In their own module so the
storage layer can raise them without importing core.Vault__Errors' transport
re-exports."""


class Vault__Scoped_Clone_Error(Exception):
    """An operation that needs the whole vault (or its whole history) was run
    on a partial clone, or a write landed outside the clone's folders."""

    def __init__(self, message: str = 'this clone holds only part of the vault'):
        super().__init__(message)
