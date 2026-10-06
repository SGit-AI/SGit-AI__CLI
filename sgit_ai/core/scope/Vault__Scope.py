"""Re-export: the scope model lives in the storage layer (pure path logic the
tree reader needs; storage may not import core). Callers in core/workflow/cli
import it from here."""
from sgit_ai.storage.Vault__Scope import Vault__Scope      # noqa: F401
