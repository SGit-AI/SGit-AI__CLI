"""Clone__Workspace — Workflow__Workspace extended with non-serialisable clone context."""
import os

from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Clone__Workspace(Workflow__Workspace):
    """Adds non-serialisable manager objects needed across all clone steps."""

    sync_client        : object = None   # Vault__Sync__Clone instance
    on_progress        : object = None   # callable | None
    storage            : object = None   # Vault__Storage
    pki                : object = None   # PKI__Crypto
    key_manager        : object = None   # Vault__Key_Manager
    ref_manager        : object = None   # Vault__Ref_Manager
    obj_store          : object = None   # Vault__Object_Store
    branch_manager     : object = None   # Vault__Branch_Manager
    vc                 : object = None   # Vault__Commit
    sub_tree           : object = None   # Vault__Sub_Tree
    integrity_failures : list            # file_ids refused by SP-1 verify-before-write
    integrity_authenticated : list       # file_ids accepted only by the key-fallback (A1)

    def ensure_managers(self, sg_dir: str) -> None:
        """Build all manager objects from sg_dir. Safe to call multiple times."""
        if self.storage is not None:
            return
        from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
        from sgit_ai.crypto.Vault__Key_Manager   import Vault__Key_Manager
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Branch_Manager  import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Storage         import Vault__Storage
        from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree

        crypto              = self.sync_client.crypto
        self.storage        = Vault__Storage()
        self.pki            = PKI__Crypto()
        self.key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto)
        self.ref_manager    = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        self.obj_store      = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        self.branch_manager = Vault__Branch_Manager(
            vault_path  = sg_dir,
            crypto      = crypto,
            key_manager = self.key_manager,
            ref_manager = self.ref_manager,
            storage     = self.storage,
        )
        self.vc       = Vault__Commit(crypto=crypto, pki=self.pki,
                                      object_store=self.obj_store,
                                      ref_manager=self.ref_manager)
        self.sub_tree = Vault__Sub_Tree(crypto=crypto, obj_store=self.obj_store)

    def save_file(self, sg_dir: str, file_id: str, data: bytes, read_key: bytes = None) -> bool:
        """Write a downloaded file to the bare store — after id-verifying it.

        SP-1 / invariant I7: an obj-cas-imm-* payload whose bytes do not hash
        to its id is refused, not written; the failure is recorded and the run
        continues (per-object fail-soft). The path is also contained by
        Vault__Path_Guard, since file_id names the on-disk location. read_key
        enables the post-move fallback (see Vault__Verified_Write.verify).
        """
        from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
        writer  = Vault__Verified_Write(crypto=self.sync_client.crypto)
        verdict = writer.save(sg_dir, file_id, data, read_key=read_key)
        if verdict == Vault__Verified_Write.REFUSED:
            self.integrity_failures.append(file_id)
            self.progress('warning', 'Object failed integrity check — skipped',
                          f'{file_id}: bytes do not hash to the id (or unsafe path); not written')
            return False
        if verdict == Vault__Verified_Write.AUTHENTICATED:      # A1: fallback fired — surface it
            self.integrity_authenticated.append(file_id)
        return True

    def progress(self, event: str, message: str, detail: str = '') -> None:
        """Fire the progress callback if set."""
        if self.on_progress:
            self.on_progress(event, message, detail)
