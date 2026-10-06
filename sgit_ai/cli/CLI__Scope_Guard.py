"""CLI__Scope_Guard — whole-vault commands refuse on a partial (scoped / shallow) clone.

fsck, dump, publish and vault move read or rewrite every object the vault
has; a clone that holds one folder, or one commit of history, would report
the rest as missing or publish a hole. The guard names what the clone holds
and how to widen it, and is a no-op for a full clone (or anything that is
not a vault — the command reports that itself)."""
from osbot_utils.type_safe.Type_Safe       import Type_Safe
from sgit_ai.core.Vault__Errors            import Vault__Scoped_Clone_Error


class CLI__Scope_Guard(Type_Safe):

    def require_whole(self, directory: str, command: str) -> None:
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.core.Vault__Sync         import Vault__Sync
        from sgit_ai.network.api.Vault__API   import Vault__API
        try:
            scope = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API()).scope_of(directory)
        except Exception:
            return
        if scope.is_partial():
            raise Vault__Scoped_Clone_Error(
                f'`{command}` needs the whole vault, and this clone holds only part of it '
                f'({scope.describe()}). Run it from a full clone, or widen this one: '
                f'`sgit fetch <folder>` adds a folder, `sgit fetch --unshallow` fetches the history.')
