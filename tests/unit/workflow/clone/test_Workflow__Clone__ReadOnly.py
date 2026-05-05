"""Tests for Workflow__Clone__ReadOnly — 9-step read-only clone pipeline."""
import copy
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto                             import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory                import Vault__API__In_Memory
from sgit_ai.core.Vault__Sync                                 import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone            import Vault__Sync__Clone
from sgit_ai.schemas.workflow.clone.Schema__Clone__State      import Schema__Clone__State
from sgit_ai.safe_types.Safe_Str__File_Path                   import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id                    import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Read_Key                    import Safe_Str__Read_Key
from sgit_ai.workflow.Workflow__Runner                        import Workflow__Runner
from sgit_ai.workflow.clone.Clone__Workspace                  import Clone__Workspace
from sgit_ai.workflow.clone.Step__Clone__ReadOnly__Set_Keys   import Step__Clone__ReadOnly__Set_Keys
from sgit_ai.workflow.clone.Step__Clone__ReadOnly__Setup_Config import Step__Clone__ReadOnly__Setup_Config
from sgit_ai.workflow.clone.Workflow__Clone__ReadOnly         import Workflow__Clone__ReadOnly
from sgit_ai.workflow.clone.Step__Clone__Check_Directory      import Step__Clone__Check_Directory
from sgit_ai.workflow.clone.Step__Clone__Download_Index       import Step__Clone__Download_Index
from sgit_ai.workflow.clone.Step__Clone__Download_Branch_Meta import Step__Clone__Download_Branch_Meta
from sgit_ai.workflow.clone.Step__Clone__Walk_Commits         import Step__Clone__Walk_Commits
from sgit_ai.workflow.clone.Step__Clone__Walk_Trees           import Step__Clone__Walk_Trees
from sgit_ai.workflow.clone.Step__Clone__Download_Blobs       import Step__Clone__Download_Blobs
from sgit_ai.workflow.clone.Step__Clone__Extract_Working_Copy import Step__Clone__Extract_Working_Copy


VAULT_KEY = 'ro-test:wftest01'
FILES     = {'hello.txt': b'hello read-only', 'sub/data.txt': b'nested ro file'}


def _build_snapshot(vault_key: str, files: dict) -> dict:
    crypto   = Vault__Crypto()
    api      = Vault__API__In_Memory()
    api.setup()
    sync     = Vault__Sync(crypto=crypto, api=api)
    snap_dir = tempfile.mkdtemp(prefix='clone_ro_src_')
    vault_dir = os.path.join(snap_dir, 'vault')

    sync.init(vault_dir, vault_key=vault_key)
    for rel_path, content in files.items():
        full = os.path.join(vault_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(content if isinstance(content, bytes) else content.encode())
    sync.commit(vault_dir, message='initial ro commit')
    sync.push(vault_dir)

    snapshot_store = copy.deepcopy(api._store)
    sync_clone     = Vault__Sync__Clone(crypto=crypto, api=api)
    keys           = sync_clone._derive_keys_from_stored_key(vault_key)
    shutil.rmtree(snap_dir, ignore_errors=True)
    return {'crypto': crypto, 'snapshot_store': snapshot_store, 'vault_key': vault_key,
            'vault_id': keys['vault_id'], 'read_key_hex': keys['read_key']}


class Test_Workflow__Clone__ReadOnly__Structure:

    def test_workflow_name(self):
        assert Workflow__Clone__ReadOnly().workflow_name() == 'clone-read-only'

    def test_workflow_version(self):
        assert Workflow__Clone__ReadOnly().workflow_version() == '1.0.0'

    def test_step_count(self):
        assert len(Workflow__Clone__ReadOnly().step_classes()) == 9

    def test_step_order(self):
        classes = Workflow__Clone__ReadOnly().step_classes()
        assert classes[0] is Step__Clone__ReadOnly__Set_Keys
        assert classes[1] is Step__Clone__Check_Directory
        assert classes[2] is Step__Clone__Download_Index
        assert classes[3] is Step__Clone__Download_Branch_Meta
        assert classes[4] is Step__Clone__Walk_Commits
        assert classes[5] is Step__Clone__Walk_Trees
        assert classes[6] is Step__Clone__Download_Blobs
        assert classes[7] is Step__Clone__Extract_Working_Copy
        assert classes[8] is Step__Clone__ReadOnly__Setup_Config

    def test_step_names(self):
        names = [sc().step_name() for sc in Workflow__Clone__ReadOnly().step_classes()]
        assert names == [
            'readonly-set-keys',
            'check-directory',
            'download-index',
            'download-branch-meta',
            'walk-commits',
            'walk-trees',
            'download-blobs',
            'extract-working-copy',
            'readonly-setup-config',
        ]

    def test_all_steps_use_clone_state_schema(self):
        for sc in Workflow__Clone__ReadOnly().step_classes():
            step = sc()
            assert step.input_schema  is Schema__Clone__State
            assert step.output_schema is Schema__Clone__State

    def test_workflow_is_registered(self):
        from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow import CLI__Dev__Workflow
        known = CLI__Dev__Workflow._known_workflows()
        assert 'clone-read-only' in known


class Test_Workflow__Clone__ReadOnly__Pipeline:

    _snapshot: dict = None

    @classmethod
    def setup_class(cls):
        cls._snapshot = _build_snapshot(VAULT_KEY, FILES)

    def setup_method(self):
        self.tmp       = tempfile.mkdtemp(prefix='clone_ro_dst_')
        self.clone_dir = os.path.join(self.tmp, 'cloned')

        crypto = self._snapshot['crypto']
        api    = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snapshot['snapshot_store'])

        self.sync_clone  = Vault__Sync__Clone(crypto=crypto, api=api)
        self.vault_id    = self._snapshot['vault_id']
        self.read_key    = self._snapshot['read_key_hex']

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_workflow(self, sparse=False) -> dict:
        wf  = Workflow__Clone__ReadOnly()
        ws  = Clone__Workspace.create(wf.workflow_name(), self.tmp)
        ws.sync_client = self.sync_clone
        ws.on_progress = None
        initial = Schema__Clone__State(
            vault_id     = Safe_Str__Vault_Id(self.vault_id),
            read_key_hex = Safe_Str__Read_Key(self.read_key),
            directory    = Safe_Str__File_Path(self.clone_dir),
            sparse       = sparse,
        )
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        return runner.run(input=initial)

    def test_clone_creates_target_directory(self):
        self._run_workflow()
        assert os.path.isdir(self.clone_dir)

    def test_clone_creates_sg_vault(self):
        self._run_workflow()
        assert os.path.isdir(os.path.join(self.clone_dir, '.sg_vault'))

    def test_clone_extracts_working_files(self):
        self._run_workflow()
        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))
        assert open(os.path.join(self.clone_dir, 'hello.txt'), 'rb').read() == b'hello read-only'

    def test_clone_extracts_nested_files(self):
        self._run_workflow()
        assert os.path.isfile(os.path.join(self.clone_dir, 'sub', 'data.txt'))

    def test_sparse_clone_skips_working_files(self):
        self._run_workflow(sparse=True)
        assert not os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))
        assert os.path.isdir(os.path.join(self.clone_dir, '.sg_vault'))

    def test_no_vault_key_file_written(self):
        self._run_workflow()
        vk_path = os.path.join(self.clone_dir, '.sg_vault', 'local', 'vault_key')
        assert not os.path.isfile(vk_path)

    def test_clone_mode_json_written_as_read_only(self):
        import json
        self._run_workflow()
        cm_path = os.path.join(self.clone_dir, '.sg_vault', 'local', 'clone_mode.json')
        assert os.path.isfile(cm_path)
        with open(cm_path) as f:
            data = json.load(f)
        assert data.get('mode') == 'read-only'

    def test_clone_mode_json_contains_vault_id(self):
        import json
        self._run_workflow()
        cm_path = os.path.join(self.clone_dir, '.sg_vault', 'local', 'clone_mode.json')
        with open(cm_path) as f:
            data = json.load(f)
        assert data.get('vault_id') == self.vault_id

    def test_returns_mode_read_only(self):
        out = self.sync_clone.clone_read_only(
            vault_id    = self.vault_id,
            read_key_hex = self.read_key,
            directory   = self.clone_dir,
        )
        assert out.get('mode') == 'read-only'

    def test_via_facade_extracts_files(self):
        self.sync_clone.clone_read_only(
            vault_id    = self.vault_id,
            read_key_hex = self.read_key,
            directory   = self.clone_dir,
        )
        assert os.path.isfile(os.path.join(self.clone_dir, 'hello.txt'))

    def test_byte_identical_output_vs_original_implementation(self):
        """Read-only clone via workflow produces same working copy as full clone on same vault."""
        full_clone_dir = os.path.join(self.tmp, 'full_cloned')
        sync_full = Vault__Sync__Clone(
            crypto = self._snapshot['crypto'],
            api    = Vault__API__In_Memory(),
        )
        sync_full.api.setup()
        sync_full.api._store = copy.deepcopy(self._snapshot['snapshot_store'])
        full_clone = Vault__Sync(crypto=self._snapshot['crypto'], api=sync_full.api)
        full_clone.clone(VAULT_KEY, full_clone_dir)

        self.sync_clone.clone_read_only(
            vault_id     = self.vault_id,
            read_key_hex = self.read_key,
            directory    = self.clone_dir,
        )

        for rel_path in ['hello.txt', 'sub/data.txt']:
            full_content = open(os.path.join(full_clone_dir, rel_path), 'rb').read()
            ro_content   = open(os.path.join(self.clone_dir,  rel_path), 'rb').read()
            assert full_content == ro_content, f'File mismatch: {rel_path}'
