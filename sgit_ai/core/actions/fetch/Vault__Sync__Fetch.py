"""Vault__Sync__Fetch — fetch-only facade: downloads remote objects without merging."""
import os

from sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base


class Vault__Sync__Fetch(Vault__Sync__Base):

    def fetch(self, directory: str, on_progress: callable = None) -> dict:
        """Download remote commits, trees, and blobs for the named branch without merging.

        Uses Workflow__Fetch (4 steps): derive_keys → load_branch_info →
        fetch_remote_ref → fetch_missing.

        Returns a dict with n_objects_fetched and named_commit_id.
        """
        from sgit_ai.workflow.fetch.Workflow__Fetch    import Workflow__Fetch
        from sgit_ai.workflow.fetch.Fetch__Workspace   import Fetch__Workspace
        from sgit_ai.workflow.Workflow__Runner         import Workflow__Runner
        from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State import Schema__Fetch__State
        from sgit_ai.safe_types.Safe_Str__File_Path    import Safe_Str__File_Path
        from sgit_ai.storage.Vault__Storage            import SG_VAULT_DIR

        wf       = Workflow__Fetch()
        work_dir = os.path.join(directory, SG_VAULT_DIR, 'work')
        os.makedirs(work_dir, exist_ok=True)
        ws             = Fetch__Workspace.create(wf.workflow_name(), work_dir,
                                                 wf.workflow_version())
        ws.sync_client = self
        ws.on_progress = on_progress
        initial        = Schema__Fetch__State(directory=Safe_Str__File_Path(directory))
        runner         = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final_dict     = runner.run(input=initial)

        n_fetched      = final_dict.get('n_objects_fetched', 0) or 0
        named_commit   = final_dict.get('named_commit_id', '') or ''
        return dict(
            status            = 'fetched',
            n_objects_fetched = int(str(n_fetched)) if n_fetched else 0,
            named_commit_id   = str(named_commit) if named_commit else '',
        )
