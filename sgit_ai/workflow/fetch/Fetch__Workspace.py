"""Fetch__Workspace — Workflow__Workspace extended with non-serialisable fetch context."""
from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Fetch__Workspace(Workflow__Workspace):
    """Adds non-serialisable manager objects needed across all fetch steps."""

    sync_client    : object = None   # Vault__Sync__Pull instance (fetch is a subset of pull)
    on_progress    : object = None   # callable | None
    storage        : object = None   # Vault__Storage
    pki            : object = None   # PKI__Crypto
    ref_manager    : object = None   # Vault__Ref_Manager
    obj_store      : object = None   # Vault__Object_Store
    branch_manager : object = None   # Vault__Branch_Manager

    def ensure_managers(self, sg_dir: str) -> None:
        """Build all manager objects from sg_dir. Safe to call multiple times."""
        if self.storage is not None:
            return
        from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
        from sgit_ai.crypto.Vault__Key_Manager     import Vault__Key_Manager
        from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Storage        import Vault__Storage

        crypto              = self.sync_client.crypto
        self.storage        = Vault__Storage()
        self.pki            = PKI__Crypto()
        key_manager         = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto)
        self.ref_manager    = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        self.obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        self.branch_manager = Vault__Branch_Manager(
            vault_path  = sg_dir,
            crypto      = crypto,
            key_manager = key_manager,
            ref_manager = self.ref_manager,
            storage     = self.storage,
        )

    def progress(self, event: str, message: str, detail: str = '') -> None:
        """Fire the progress callback if set."""
        if self.on_progress:
            self.on_progress(event, message, detail)
