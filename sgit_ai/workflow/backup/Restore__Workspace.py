"""Restore__Workspace — Workflow__Workspace for vault restore."""
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Restore__Workspace(Workflow__Workspace):
    """Workspace for vault restore — no extra manager objects needed."""

    vault_key_prompt_fn : object = None   # callable | None — injected for interactive prompts
