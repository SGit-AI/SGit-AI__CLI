"""Execution-path coverage tests for all four fetch workflow steps."""
import os

import pytest

from sgit_ai.safe_types.Safe_Str__Branch_Id    import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id    import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__File_Path    import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Index_Id     import Safe_Str__Index_Id
from sgit_ai.safe_types.Safe_Str__Ref_Id       import Safe_Str__Ref_Id
from sgit_ai.safe_types.Safe_Str__Vault_Id     import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Read_Key     import Safe_Str__Read_Key
from sgit_ai.safe_types.Safe_Str__Write_Key    import Safe_Str__Write_Key
from sgit_ai.schemas.workflow.fetch.Schema__Fetch__State import Schema__Fetch__State

from sgit_ai.workflow.fetch.Step__Fetch__Derive_Keys      import Step__Fetch__Derive_Keys
from sgit_ai.workflow.fetch.Step__Fetch__Load_Branch_Info  import Step__Fetch__Load_Branch_Info
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Remote_Ref  import Step__Fetch__Fetch_Remote_Ref
from sgit_ai.workflow.fetch.Step__Fetch__Fetch_Missing     import Step__Fetch__Fetch_Missing

# ── constants ─────────────────────────────────────────────────────────────────
READ_KEY_HEX    = 'aa' * 32
VAULT_ID        = 'testvlt1'
IDX_FILE_ID     = 'idx-pid-muw-aabbccdd1234'
CLONE_REF_ID    = 'ref-pid-muw-aabbccdd1234'
NAMED_REF_ID    = 'ref-pid-snw-aabbccdd1234'
CLONE_BRANCH_ID = 'branch-clone-aabbccdd'
COMMIT_A        = 'obj-cas-imm-aabb000001'
COMMIT_B        = 'obj-cas-imm-aabb000002'


def _base_state(sg_dir='', directory='/tmp/testdir', **kwargs) -> Schema__Fetch__State:
    return Schema__Fetch__State(
        vault_id              = Safe_Str__Vault_Id(VAULT_ID),
        read_key_hex          = Safe_Str__Read_Key(READ_KEY_HEX),
        branch_index_file_id  = Safe_Str__Index_Id(IDX_FILE_ID),
        sg_dir                = Safe_Str__File_Path(sg_dir),
        directory             = Safe_Str__File_Path(directory),
        named_ref_id          = Safe_Str__Ref_Id(NAMED_REF_ID),
        **kwargs,
    )


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeBranchMeta:
    def __init__(self, ref_id):
        self.head_ref_id = ref_id


class FakeBranchManager:
    def __init__(self, return_clone=True, return_named=True):
        self._return_clone = return_clone
        self._return_named = return_named

    def load_branch_index(self, directory, file_id, read_key):
        return {}

    def get_branch_by_id(self, index, branch_id):
        return FakeBranchMeta(CLONE_REF_ID) if self._return_clone else None

    def get_branch_by_name(self, index, name):
        return FakeBranchMeta(NAMED_REF_ID) if self._return_named else None


class FakeLocalConfig:
    my_branch_id = CLONE_BRANCH_ID


class FakeRefManager:
    def __init__(self, ref_value=''):
        self._ref_value = ref_value

    def read_ref(self, ref_id, read_key):
        return self._ref_value


class FakeAPI:
    def __init__(self, read_return=None):
        self._read_return = read_return

    def read(self, vault_id, file_id):
        return self._read_return


class FakeSyncClient:
    def __init__(self, api=None):
        self.api    = api or FakeAPI()
        self.crypto = object()

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

    def _fetch_missing_objects(self, vault_id, commit_id, obj_store, read_key,
                                sg_dir, _p=None, stop_at=None, include_blobs=True):
        return {'n_fetched': 5}


class FakeWorkspace:
    def __init__(self, api=None, ref_value=''):
        self.sync_client    = FakeSyncClient(api=api)
        self.branch_manager = FakeBranchManager()
        self.ref_manager    = FakeRefManager(ref_value=ref_value)
        self.obj_store      = object()
        self.on_progress    = None

    def ensure_managers(self, sg_dir):
        pass

    def progress(self, tag, msg):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Derive Keys
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Fetch__Derive_Keys:

    def test_derive_keys_sets_vault_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID

    def test_derive_keys_sets_read_key_hex(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.read_key_hex) == READ_KEY_HEX

    def test_derive_keys_sets_branch_index_file_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Fetch__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Fetch__Derive_Keys().execute(state, ws)
        assert str(out.branch_index_file_id) == IDX_FILE_ID


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Load Branch Info
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Fetch__Load_Branch_Info:

    def test_loads_named_ref_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Load_Branch_Info().execute(state, ws)
        assert out.named_ref_id is not None

    def test_clone_branch_not_found_raises(self, tmp_path):
        ws                = FakeWorkspace()
        ws.branch_manager = FakeBranchManager(return_clone=False)
        state             = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Clone branch not found'):
            Step__Fetch__Load_Branch_Info().execute(state, ws)

    def test_named_branch_not_found_raises(self, tmp_path):
        ws                = FakeWorkspace()
        ws.branch_manager = FakeBranchManager(return_named=False)
        state             = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Named branch "current" not found'):
            Step__Fetch__Load_Branch_Info().execute(state, ws)

    def test_preserves_vault_id_in_output(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Load_Branch_Info().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID

    def test_clone_commit_read_from_ref(self, tmp_path):
        ws    = FakeWorkspace(ref_value=COMMIT_A)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Load_Branch_Info().execute(state, ws)
        assert str(out.clone_commit_id) == COMMIT_A


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Fetch Remote Ref
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Fetch__Fetch_Remote_Ref:

    def test_not_reachable_when_api_returns_none(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=None), ref_value='')
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is False

    def test_reachable_when_api_returns_data(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=b'ref-data'), ref_value=COMMIT_B)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is True

    def test_named_commit_id_populated(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=None), ref_value=COMMIT_B)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Fetch_Remote_Ref().execute(state, ws)
        assert str(out.named_commit_id) == COMMIT_B

    def test_api_exception_handled_gracefully(self, tmp_path):
        class ErrorAPI:
            def read(self, vault_id, file_id): raise OSError('network error')

        ws    = FakeWorkspace(api=ErrorAPI(), ref_value='')
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Fetch__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is False

    def test_ref_written_to_disk(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=b'blob'), ref_value=COMMIT_B)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        Step__Fetch__Fetch_Remote_Ref().execute(state, ws)
        ref_path = os.path.join(str(tmp_path), f'bare/refs/{NAMED_REF_ID}')
        assert os.path.isfile(ref_path)


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Fetch Missing
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Fetch__Fetch_Missing:

    def test_skips_when_no_named_commit(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path),
                            clone_commit_id=Safe_Str__Commit_Id(COMMIT_A))
        out   = Step__Fetch__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 0

    def test_skips_when_commits_identical(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Fetch__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 0

    def test_fetches_when_commits_differ(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Fetch__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 5

    def test_output_preserves_vault_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path))
        out   = Step__Fetch__Fetch_Missing().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID
