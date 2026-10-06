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
            Vault__Sync(crypto=Vault__Crypto(), api=Vault__API()).require_whole(directory, command)
        except Vault__Scoped_Clone_Error:
            raise
        except Exception:
            return                                     # not a vault / unreadable config: the command reports that itself
