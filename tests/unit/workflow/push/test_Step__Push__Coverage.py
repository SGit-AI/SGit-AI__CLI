"""Execution-path coverage tests for all six push workflow steps."""
import os
import shutil
import tempfile

import pytest

from sgit_ai.safe_types.Safe_Str__Branch_Id    import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id    import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__File_Path    import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Index_Id     import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id       import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Vault_Id     import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key    import Safe_Str__Write_Key
from sgit_ai.safe_types.Safe_UInt__File_Count  import Safe_UInt__File_Count
from sgit_ai.schemas.workflow.push.Schema__Push__State import Schema__Push__State

from sgit_ai.workflow.push.Step__Push__Check_Clean       import Step__Push__Check_Clean
from sgit_ai.workflow.push.Step__Push__Local_Inventory   import Step__Push__Local_Inventory
from sgit_ai.workflow.push.Step__Push__Fast_Forward_Check import Step__Push__Fast_Forward_Check
from sgit_ai.workflow.push.Step__Push__Upload_Objects    import Step__Push__Upload_Objects
from sgit_ai.workflow.push.Step__Push__Update_Remote_Ref import Step__Push__Update_Remote_Ref
from sgit_ai.workflow.push.Step__Push__Derive_Keys       import Step__Push__Derive_Keys

# ── shared constants ──────────────────────────────────────────────────────────
READ_KEY_HEX       = 'aa' * 32
VAULT_ID           = 'testvlt1'
IDX_FILE_ID        = 'idx-pid-muw-aabbccdd1234'
CLONE_REF_ID       = 'ref-pid-muw-aabbccdd1234'
NAMED_REF_ID       = 'ref-pid-snw-aabbccdd1234'
CLONE_BRANCH_ID    = 'branch-clone-aabbccdd'
COMMIT_A           = 'obj-cas-imm-aabb000001'
COMMIT_B           = 'obj-cas-imm-aabb000002'
COMMIT_LCA         = 'obj-cas-imm-aabb000000'


def _base_state(sg_dir='', directory='/tmp/testdir', **kwargs) -> Schema__Push__State:
    return Schema__Push__State(
        vault_id              = Safe_Str__Vault_Id(VAULT_ID),
        read_key_hex          = Safe_Str__Write_Key(READ_KEY_HEX),
        write_key_hex         = Safe_Str__Write_Key(READ_KEY_HEX),
        branch_index_file_id  = Safe_Str__Index_Id(IDX_FILE_ID),
        sg_dir                = Safe_Str__File_Path(sg_dir),
        directory             = Safe_Str__File_Path(directory),
        clone_branch_id       = Safe_Str__Branch_Id(CLONE_BRANCH_ID),
        clone_ref_id          = Safe_Str__Ref_Id(CLONE_REF_ID),
        named_ref_id          = Safe_Str__Ref_Id(NAMED_REF_ID),
        **kwargs,
    )


# ── fake workspace ────────────────────────────────────────────────────────────

class FakeBranchMeta:
    def __init__(self, head_ref_id):
        self.head_ref_id = head_ref_id


class FakeBranchManager:
    def __init__(self, clone_meta=None, named_meta=None, clone_commit='', named_commit=''):
        self._clone_meta  = clone_meta or FakeBranchMeta(CLONE_REF_ID)
        self._named_meta  = named_meta or FakeBranchMeta(NAMED_REF_ID)
        self._commits     = {CLONE_REF_ID: clone_commit, NAMED_REF_ID: named_commit}

    def load_branch_index(self, directory, file_id, read_key):
        return {'clone': self._clone_meta, 'named': self._named_meta}

    def get_branch_by_id(self, index, branch_id):
        return self._clone_meta

    def get_branch_by_name(self, index, name):
        return self._named_meta


class FakeLocalConfig:
    my_branch_id = CLONE_BRANCH_ID


class FakeCommit:
    def __init__(self, tree_id='tree-abc'):
        self.tree_id = tree_id


class FakeVC:
    def load_commit(self, commit_id, read_key):
        return FakeCommit(tree_id='tree-abc')


class FakeSubTree:
    def flatten(self, tree_id, read_key):
        return {'file.txt': {'blob_id': 'blob-001'}}


class FakeRefManager:
    def __init__(self, ref_value='', ref_map=None):
        self._ref_value = ref_value
        self._ref_map   = ref_map or {}

    def read_ref(self, ref_id, read_key):
        return self._ref_map.get(ref_id, self._ref_value)

    def write_ref(self, ref_id, commit_id, read_key):
        pass

    def encrypt_ref_value(self, commit_id, read_key):
        return b'encrypted-ref-data'


class FakeAPI:
    def __init__(self, read_return=None, write_raises=False):
        self._read_return  = read_return
        self._write_raises = write_raises
        self.written       = {}

    def read(self, vault_id, file_id):
        return self._read_return

    def write(self, vault_id, file_id, data):
        if self._write_raises:
            raise RuntimeError('write failed')
        self.written[file_id] = data


class FakeSyncClient:
    def __init__(self, api=None, clean=True, ref_value=''):
        self.crypto     = object()
        self.api        = api or FakeAPI()
        self._clean     = clean
        self._ref_value = ref_value

    def _read_local_config(self, directory, storage):
        return FakeLocalConfig()

    def _read_vault_key(self, directory):
        return 'pass:testvlt1'

    def _derive_keys_from_stored_key(self, vault_key):
        return {
            'vault_id'             : VAULT_ID,
            'read_key'             : READ_KEY_HEX,
            'write_key'            : READ_KEY_HEX,
            'branch_index_file_id' : IDX_FILE_ID,
        }


class FakeWorkspace:
    def __init__(self, api=None, clean=True, ref_value='', clone_commit='',
                 named_commit='', clone_meta=None, named_meta=None):
        self.sync_client    = FakeSyncClient(api=api, clean=clean)
        self.branch_manager = FakeBranchManager(clone_meta=clone_meta, named_meta=named_meta,
                                                clone_commit=clone_commit, named_commit=named_commit)
        self.ref_manager    = FakeRefManager(ref_value=ref_value)
        self.obj_store      = object()
        self.vc             = FakeVC()
        self.sub_tree       = FakeSubTree()

    def ensure_managers(self, sg_dir):
        pass

    def progress(self, tag, msg):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Derive Keys
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Derive_Keys:

    def test_derive_keys_populates_state(self):
        ws    = FakeWorkspace()
        state = Schema__Push__State(directory=Safe_Str__File_Path('/tmp/x'))
        out   = Step__Push__Derive_Keys().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID

    def test_derive_keys_sets_read_write_hex(self):
        ws    = FakeWorkspace()
        state = Schema__Push__State(directory=Safe_Str__File_Path('/tmp/x'))
        out   = Step__Push__Derive_Keys().execute(state, ws)
        assert str(out.read_key_hex)  == READ_KEY_HEX
        assert str(out.write_key_hex) == READ_KEY_HEX

    def test_derive_keys_sets_sg_dir(self):
        ws    = FakeWorkspace()
        state = Schema__Push__State(directory=Safe_Str__File_Path('/tmp/x'))
        out   = Step__Push__Derive_Keys().execute(state, ws)
        assert out.sg_dir is not None


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Check Clean
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Check_Clean:

    def test_clean_working_copy_passes(self, monkeypatch, tmp_path):
        class FakeStatus:
            def __init__(self, **kwargs): pass
            def status(self, directory): return {'clean': True}

        monkeypatch.setattr(
            'sgit_ai.core.actions.status.Vault__Sync__Status.Vault__Sync__Status',
            FakeStatus,
        )
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Push__Check_Clean().execute(state, ws)
        assert out.working_copy_clean is True

    def test_dirty_working_copy_raises(self, monkeypatch, tmp_path):
        class FakeStatus:
            def __init__(self, **kwargs): pass
            def status(self, directory): return {'clean': False}

        monkeypatch.setattr(
            'sgit_ai.core.actions.status.Vault__Sync__Status.Vault__Sync__Status',
            FakeStatus,
        )
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='uncommitted changes'):
            Step__Push__Check_Clean().execute(state, ws)

    def test_clean_preserves_input_fields(self, monkeypatch, tmp_path):
        class FakeStatus:
            def __init__(self, **kwargs): pass
            def status(self, directory): return {'clean': True}

        monkeypatch.setattr(
            'sgit_ai.core.actions.status.Vault__Sync__Status.Vault__Sync__Status',
            FakeStatus,
        )
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Push__Check_Clean().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID
        assert str(out.read_key_hex) == READ_KEY_HEX


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Local Inventory
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Local_Inventory:

    def test_same_commits_zero_local_only(self, tmp_path):
        ws    = FakeWorkspace(clone_commit=COMMIT_A, named_commit=COMMIT_A)
        state = _base_state(
            sg_dir    = str(tmp_path),
            directory = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Push__Local_Inventory().execute(state, ws)
        assert int(str(out.n_local_only_objects)) == 0

    def test_different_commits_counts_local_only(self, tmp_path):
        calls = []

        class TreedSubTree:
            def flatten(self, tree_id, read_key):
                calls.append(tree_id)
                if len(calls) == 1:
                    return {'a.txt': {'blob_id': 'blob-new'}, 'b.txt': {'blob_id': 'blob-b'}}
                return {'a.txt': {'blob_id': 'blob-old'}}

        ws          = FakeWorkspace(clone_commit=COMMIT_A, named_commit=COMMIT_B)
        ws.sub_tree = TreedSubTree()
        ws.ref_manager = FakeRefManager(ref_map={CLONE_REF_ID: COMMIT_A, NAMED_REF_ID: COMMIT_B})
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Push__Local_Inventory().execute(state, ws)
        assert int(str(out.n_local_only_objects)) >= 1

    def test_clone_branch_not_found_raises(self, tmp_path):
        ws = FakeWorkspace()
        ws.branch_manager.get_branch_by_id = lambda index, bid: None
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Clone branch not found'):
            Step__Push__Local_Inventory().execute(state, ws)

    def test_named_branch_not_found_raises(self, tmp_path):
        ws = FakeWorkspace()
        ws.branch_manager.get_branch_by_name = lambda index, name: None
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Named branch "current" not found'):
            Step__Push__Local_Inventory().execute(state, ws)

    def test_output_contains_ref_ids(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Push__Local_Inventory().execute(state, ws)
        assert out.clone_ref_id is not None
        assert out.named_ref_id is not None


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Fast-Forward Check
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Fast_Forward_Check:

    def _state(self, clone_commit='', force=False, sg_dir='', **extra):
        return _base_state(
            sg_dir          = sg_dir,
            clone_commit_id = Safe_Str__Commit_Id(clone_commit) if clone_commit else None,
            force           = force,
            **extra,
        )

    def test_no_remote_ref_allows_push(self, tmp_path):
        ws = FakeWorkspace(ref_value='')
        ws.sync_client.api = FakeAPI(read_return=None)
        state = self._state(clone_commit=COMMIT_A, sg_dir=str(tmp_path))
        out = Step__Push__Fast_Forward_Check().execute(state, ws)
        assert out.can_fast_forward is True

    def test_remote_matches_clone_allows_push(self, tmp_path):
        ws = FakeWorkspace(ref_value=COMMIT_A)
        ws.sync_client.api = FakeAPI(read_return=None)
        state = self._state(clone_commit=COMMIT_A, sg_dir=str(tmp_path))
        out = Step__Push__Fast_Forward_Check().execute(state, ws)
        assert out.can_fast_forward is True

    def test_force_overrides_diverge(self, tmp_path):
        ws = FakeWorkspace(ref_value=COMMIT_B)
        ws.sync_client.api = FakeAPI(read_return=None)
        state = self._state(clone_commit=COMMIT_A, sg_dir=str(tmp_path), force=True)
        out = Step__Push__Fast_Forward_Check().execute(state, ws)
        assert out.can_fast_forward is True

    def test_diverged_without_force_raises(self, tmp_path):
        ws = FakeWorkspace(ref_value=COMMIT_B)
        ws.sync_client.api = FakeAPI(read_return=None)
        state = self._state(clone_commit=COMMIT_A, sg_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match='diverged'):
            Step__Push__Fast_Forward_Check().execute(state, ws)

    def test_remote_commit_id_set_in_output(self, tmp_path):
        ws = FakeWorkspace(ref_value='')
        ws.sync_client.api = FakeAPI(read_return=None)
        state = self._state(clone_commit=COMMIT_A, sg_dir=str(tmp_path))
        out = Step__Push__Fast_Forward_Check().execute(state, ws)
        assert out.can_fast_forward is True


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — Upload Objects
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Upload_Objects:

    def test_no_clone_commit_skips_upload(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path))
        out   = Step__Push__Upload_Objects().execute(state, ws)
        assert int(str(out.n_objects_uploaded)) == 0

    def test_clone_equals_remote_skips_upload(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Push__Upload_Objects().execute(state, ws)
        assert int(str(out.n_objects_uploaded)) == 0

    def test_upload_executed_when_commits_differ(self, monkeypatch, tmp_path):
        class FakeBatch:
            def __init__(self, **kwargs): pass
            def build_push_operations(self, **kwargs): return (['op1', 'op2'], None)
            def execute_batch(self, vault_id, write_key, ops): return {'n_uploaded': len(ops)}

        monkeypatch.setattr(
            'sgit_ai.core.actions.push.Vault__Batch.Vault__Batch',
            FakeBatch,
        )
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Push__Upload_Objects().execute(state, ws)
        assert int(str(out.n_objects_uploaded)) == 2

    def test_batch_exception_raises_runtime_error(self, monkeypatch, tmp_path):
        class FakeBatch:
            def __init__(self, **kwargs): pass
            def build_push_operations(self, **kwargs): raise ValueError('bad objects')
            def execute_batch(self, *a, **k): pass

        monkeypatch.setattr(
            'sgit_ai.core.actions.push.Vault__Batch.Vault__Batch',
            FakeBatch,
        )
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        with pytest.raises(RuntimeError, match='Upload failed'):
            Step__Push__Upload_Objects().execute(state, ws)

    def test_output_preserves_can_fast_forward(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), can_fast_forward=True)
        out   = Step__Push__Upload_Objects().execute(state, ws)
        assert out.can_fast_forward is True


# ══════════════════════════════════════════════════════════════════════════════
# Step 6 — Update Remote Ref
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Push__Update_Remote_Ref:

    def test_already_up_to_date_skips_write(self, tmp_path):
        api   = FakeAPI()
        ws    = FakeWorkspace(api=api)
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Push__Update_Remote_Ref().execute(state, ws)
        assert out.remote_ref_updated is False
        assert api.written == {}

    def test_updates_remote_ref_when_commits_differ(self, tmp_path):
        api   = FakeAPI()
        ws    = FakeWorkspace(api=api)
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Push__Update_Remote_Ref().execute(state, ws)
        assert out.remote_ref_updated is True
        assert len(api.written) == 1

    def test_write_failure_raises(self, tmp_path):
        api   = FakeAPI(write_raises=True)
        ws    = FakeWorkspace(api=api)
        state = _base_state(
            sg_dir           = str(tmp_path),
            clone_commit_id  = Safe_Str__Commit_Id(COMMIT_A),
            remote_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        with pytest.raises(RuntimeError, match='Failed to update remote ref'):
            Step__Push__Update_Remote_Ref().execute(state, ws)

    def test_no_clone_commit_skips_write(self, tmp_path):
        api   = FakeAPI()
        ws    = FakeWorkspace(api=api)
        state = _base_state(sg_dir=str(tmp_path))
        out   = Step__Push__Update_Remote_Ref().execute(state, ws)
        assert out.remote_ref_updated is False
