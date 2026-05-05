"""Functional test for Step__Pull__Fetch_Missing — proves the _p= kwarg fix (Bug B15-1).

Uses a real in-memory API and a real vault snapshot so the step's call to
workspace.sync_client._fetch_missing_objects() executes end-to-end without TypeError.
"""
import os
import tempfile
import shutil

from sgit_ai.core.actions.pull.Vault__Sync__Pull     import Vault__Sync__Pull
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.safe_types.Safe_Str__Commit_Id          import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__File_Path          import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Index_Id           import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Read_Key           import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Vault_Id           import Safe_Str__Vault_Id
from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State
from sgit_ai.workflow.pull.Pull__Workspace           import Pull__Workspace
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing import Step__Pull__Fetch_Missing

from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Step__Pull__Fetch_Missing__Functional:
    """Prove Bug B15-1 is fixed: _fetch_missing_objects is called with _p= not on_progress=."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': b'hello vault'})

    def setup_method(self):
        self.env    = self._env.restore()
        self.target = tempfile.mkdtemp(prefix='pull_fetch_target_')
        os.makedirs(os.path.join(self.target, '.sg_vault', 'bare', 'data'), exist_ok=True)

    def teardown_method(self):
        self.env.cleanup()
        shutil.rmtree(self.target, ignore_errors=True)

    def _build_workspace(self):
        sync_client    = Vault__Sync__Pull(crypto=self.env.crypto, api=self.env.api)
        ws             = Pull__Workspace()
        ws.sync_client = sync_client
        sg_dir         = os.path.join(self.target, '.sg_vault')
        ws.ensure_managers(sg_dir)
        return ws, sg_dir

    def _build_state(self, sg_dir, commit_id, read_key_hex, vault_id):
        return Schema__Pull__State(
            vault_id             = Safe_Str__Vault_Id(vault_id),
            read_key_hex         = Safe_Str__Read_Key(read_key_hex),
            branch_index_file_id = Safe_Str__Index_Id(''),
            sg_dir               = Safe_Str__File_Path(sg_dir),
            directory            = Safe_Str__File_Path(self.target),
            named_commit_id      = Safe_Str__Commit_Id(commit_id),
        )

    def test_fetch_missing_no_type_error(self):
        """Step calls _fetch_missing_objects with correct _p= kwarg — no TypeError."""
        ws, sg_dir = self._build_workspace()
        keys       = self.env.sync._derive_keys_from_stored_key(self.env.vault_key)
        state      = self._build_state(sg_dir, str(self.env.commit_id),
                                       keys['read_key'], keys['vault_id'])
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) >= 0

    def test_fetch_missing_downloads_objects_when_commit_differs(self):
        """Objects are fetched when named_commit_id differs from clone_commit_id."""
        ws, sg_dir = self._build_workspace()
        keys       = self.env.sync._derive_keys_from_stored_key(self.env.vault_key)
        state      = self._build_state(sg_dir, str(self.env.commit_id),
                                       keys['read_key'], keys['vault_id'])
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) > 0

    def test_fetch_missing_skips_when_commits_identical(self):
        """Step skips fetch and returns 0 when named == clone commit."""
        ws, sg_dir = self._build_workspace()
        keys       = self.env.sync._derive_keys_from_stored_key(self.env.vault_key)
        commit_id  = str(self.env.commit_id)
        state      = Schema__Pull__State(
            vault_id             = Safe_Str__Vault_Id(keys['vault_id']),
            read_key_hex         = Safe_Str__Read_Key(keys['read_key']),
            branch_index_file_id = Safe_Str__Index_Id(''),
            sg_dir               = Safe_Str__File_Path(sg_dir),
            directory            = Safe_Str__File_Path(self.target),
            named_commit_id      = Safe_Str__Commit_Id(commit_id),
            clone_commit_id      = Safe_Str__Commit_Id(commit_id),
        )
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 0
