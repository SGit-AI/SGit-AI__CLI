"""Move__Workspace — Workflow__Workspace for vault move."""
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Move__Workspace(Workflow__Workspace):
    """Workspace for vault move.

    Optional `api` attribute: if set, push and verify steps use it instead of
    creating a new Vault__API from the config URL. Required for in-memory testing.
    """
    api = None   # optional Vault__API override (plain attr, not Type_Safe field)
