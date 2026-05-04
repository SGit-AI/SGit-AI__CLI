"""Tests for Workflow__Clone — the 10-step clone pipeline."""
import copy
import os
import tempfile
import shutil

import pytest

from sgit_ai.network.api.Vault__API__In_Memory                    import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto                         import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.core.Vault__Sync                             import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone                      import Vault__Sync__Clone
from sgit_ai.workflow.Workflow__Runner                    import Workflow__Runner
from sgit_ai.workflow.clone.Clone__Workspace              import Clone__Workspace
from sgit_ai.workflow.clone.Step__Clone__Check_Directory  import Step__Clone__Check_Directory
from sgit_ai.workflow.clone.Step__Clone__Create_Clone_Branch  import Step__Clone__Create_Clone_Branch
from sgit_ai.workflow.clone.Step__Clone__Derive_Keys      import Step__Clone__Derive_Keys
from sgit_ai.workflow.clone.Step__Clone__Download_Blobs   import Step__Clone__Download_Blobs
from sgit_ai.workflow.clone.Step__Clone__Download_Branch_Meta import Step__Clone__Download_Branch_Meta
from sgit_ai.workflow.clone.Step__Clone__Download_Index   import Step__Clone__Download_Index
from sgit_ai.workflow.clone.Step__Clone__Extract_Working_Copy import Step__Clone__Extract_Working_Copy
from sgit_ai.workflow.clone.Step__Clone__Setup_Local_Config   import Step__Clone__Setup_Local_Config
from sgit_ai.workflow.clone.Step__Clone__Walk_Commits     import Step__Clone__Walk_Commits
from sgit_ai.workflow.clone.Step__Clone__Walk_Trees       import Step__Clone__Walk_Trees
from sgit_ai.workflow.clone.Workflow__Clone               import Workflow__Clone


# ---------------------------------------------------------------------------
# Workflow__Clone structure tests
# ---------------------------------------------------------------------------

class Test_Workflow__Clone__Structure:

    def test_workflow_name(self):
        assert Workflow__Clone().workflow_name() == 'clone'

    def test_workflow_version(self):
        assert Workflow__Clone().workflow_version() == '1.0.0'

    def test_step_count(self):
        assert len(Workflow__Clone().step_classes()) == 10

    def test_step_order(self):
        classes = Workflow__Clone().step_classes()
        assert classes[0]  is Step__Clone__Derive_Keys
        assert classes[1]  is Step__Clone__Check_Directory
        assert classes[2]  is Step__Clone__Download_Index
        assert classes[3]  is Step__Clone__Download_Branch_Meta
        assert classes[4]  is Step__Clone__Walk_Commits
        assert classes[5]  is Step__Clone__Walk_Trees
        assert classes[6]  is Step__Clone__Download_Blobs
        assert classes[7]  is Step__Clone__Create_Clone_Branch
        assert classes[8]  is Step__Clone__Extract_Working_Copy
        assert classes[9]  is Step__Clone__Setup_Local_Config

    def test_step_names(self):
        names = [sc().step_name() for sc in Workflow__Clone().step_classes()]
        assert names == [
            'derive-keys',
            'check-directory',
            'download-index',
            'download-branch-meta',
            'walk-commits',
            'walk-trees',
            'download-blobs',
            'create-clone-branch',
            'extract-working-copy',
            'setup-local-config',
        ]

    def test_all_steps_use_clone_state_schema(self):
        for sc in Workflow__Clone().step_classes():
            step = sc()
            assert step.input_schema  is Schema__Clone__State
            assert step.output_schema is Schema__Clone__State


class Test_Workflow__Clone__Full_Pipeline:

    _snapshot: dict = None

    VAULT_KEY = 'clonetest:cwftest01'
    FILES     = {'hello.txt': 'hello from workflow clone', 'sub/data.txt': 'nested file'}

    @classmethod
    def _build_snapshot(cls, vault_key: str, files: dict) -> dict:
        crypto   = Vault__Crypto()
        api      = Vault__API__In_Memory()
        api.setup()
        sync     = Vault__Sync(crypto=crypto, api=api)
        snap_dir = tempfile.mkdtemp(prefix='clone_wf_src_')
        vault_dir = os.path.join(snap_dir, 'vault')

        sync.init(vault_dir, vault_key=vault_key)
        for rel_path, content in files.items():
            full = os.path.join(vault_dir, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        sync.commit(vault_dir, message='initial commit')
        sync.push(vault_dir)

        snapshot_store = copy.deepcopy(api._store)
        shutil.rmtree(snap_dir, ignore_errors=True)
        return {'crypto': crypto, 'snapshot_store': snapshot_store, 'vault_key': vault_key}

    @classmethod
    def setup_class(cls):
        cls._snapshot = cls._build_snapshot(cls.VAULT_KEY, cls.FILES)

    def setup_method(self):
        self.tmp      = tempfile.mkdtemp(prefix='clone_wf_dst_')
        self.clone_dir = os.path.join(self.tmp, 'cloned')

        crypto = self._snapshot['crypto']
        api    = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snapshot['snapshot_store'])

        self.sync_clone = Vault__Sync__Clone(crypto=crypto, api=api)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_clone(self, sparse=False) -> dict:
        wf  = Workflow__Clone()
        ws  = Clone__Workspace.create(wf.workflow_name(), self.tmp)
        ws.sync_client = self.sync_clone
        ws.on_progress = None
        initial = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(self.VAULT_KEY),
            directory = Safe_Str__File_Path(self.clone_dir),
            sparse    = sparse,
        )
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        return runner.run(input=initial)

    def test_clone_creates_target_directory(self):
        self._run_clone()
        assert os.path.isdir(self.clone_dir)

    def test_clone_creates_sg_vault(self):
        self._run_clone()
        assert os.path.isdir(os.path.join(self.clone_dir, '.sg_vault'))

    def test_clone_extracts_working_files(self):
        self._run_clone()
        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))
        assert open(os.path.join(self.clone_dir, 'hello.txt')).read() == 'hello from workflow clone'

    def test_clone_extracts_nested_files(self):
        self._run_clone()
        assert os.path.isfile(os.path.join(self.clone_dir, 'sub', 'data.txt'))

    def test_clone_writes_vault_key(self):
        self._run_clone()
        vk_path = os.path.join(self.clone_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vk_path)
        assert open(vk_path).read() == self.VAULT_KEY

    def test_clone_writes_local_config(self):
        self._run_clone()
        cfg_path = os.path.join(self.clone_dir, '.sg_vault', 'local', 'config.json')
        assert os.path.isfile(cfg_path)

    def test_clone_returns_vault_id(self):
        out = self._run_clone()
        assert out.get('vault_id', '') != ''

    def test_clone_returns_clone_branch_id(self):
        out = self._run_clone()
        assert str(out.get('clone_branch_id', '')).startswith('branch-clone-')

    def test_clone_returns_commit_id(self):
        out = self._run_clone()
        assert str(out.get('named_commit_id', '')).startswith('obj-cas-imm-')

    def test_sparse_clone_skips_working_files(self):
        self._run_clone(sparse=True)
        assert not os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))
        assert os.path.isdir(os.path.join(self.clone_dir, '.sg_vault'))
