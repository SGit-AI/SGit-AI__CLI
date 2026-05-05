"""Transfer__Workspace — Workflow__Workspace for Workflow__Clone__Transfer."""
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Transfer__Workspace(Workflow__Workspace):
    """Adds non-serialisable objects needed for transfer clone steps."""

    sync_client    : object = None   # Vault__Sync__Clone instance
    on_progress    : object = None   # callable | None
    received_files : object = None   # dict[str, bytes] — populated by Step__Transfer__Receive

    def progress(self, event: str, message: str, detail: str = '') -> None:
        if self.on_progress:
            self.on_progress(event, message, detail)
