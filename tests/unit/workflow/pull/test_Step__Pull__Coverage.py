"""Execution-path coverage tests for all five pull workflow steps."""
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
from sgit_ai.schemas.workflow.pull.Schema__Pull__State import Schema__Pull__State

from sgit_ai.workflow.pull.Step__Pull__Derive_Keys      import Step__Pull__Derive_Keys
from sgit_ai.workflow.pull.Step__Pull__Load_Branch_Info  import Step__Pull__Load_Branch_Info
from sgit_ai.workflow.pull.Step__Pull__Fetch_Remote_Ref  import Step__Pull__Fetch_Remote_Ref
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing     import Step__Pull__Fetch_Missing
from sgit_ai.workflow.pull.Step__Pull__Merge             import Step__Pull__Merge

# ── shared constants ──────────────────────────────────────────────────────────
READ_KEY_HEX    = 'aa' * 32
VAULT_ID        = 'testvlt1'
IDX_FILE_ID     = 'idx-pid-muw-aabbccdd1234'
CLONE_REF_ID    = 'ref-pid-muw-aabbccdd1234'
NAMED_REF_ID    = 'ref-pid-snw-aabbccdd1234'
CLONE_BRANCH_ID = 'branch-clone-aabbccdd'
COMMIT_A        = 'obj-cas-imm-aabb000001'
COMMIT_B        = 'obj-cas-imm-aabb000002'
COMMIT_LCA      = 'obj-cas-imm-aabb000000'


def _base_state(sg_dir='', directory='/tmp/testdir', **kwargs) -> Schema__Pull__State:
    return Schema__Pull__State(
        vault_id              = Safe_Str__Vault_Id(VAULT_ID),
        read_key_hex          = Safe_Str__Write_Key(READ_KEY_HEX),
        branch_index_file_id  = Safe_Str__Index_Id(IDX_FILE_ID),
        sg_dir                = Safe_Str__File_Path(sg_dir),
        directory             = Safe_Str__File_Path(directory),
        clone_branch_id       = Safe_Str__Branch_Id(CLONE_BRANCH_ID),
        clone_ref_id          = Safe_Str__Ref_Id(CLONE_REF_ID),
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


class FakeCommit:
    def __init__(self, tree_id='tree-abc'):
        self.tree_id = tree_id


class FakeVC:
    def load_commit(self, commit_id, read_key):
        return FakeCommit()

    def create_commit(self, read_key, tree_id, parent_ids, message, branch_id):
        return 'obj-cas-imm-mergecommit'


class FakeSubTree:
    def flatten(self, tree_id, read_key):
        return {'file.txt': {'blob_id': 'blob-001'}}

    def build_from_flat(self, flat_map, read_key):
        return 'tree-merged'


class FakeRefManager:
    def __init__(self, ref_value=''):
        self._ref_value = ref_value

    def read_ref(self, ref_id, read_key):
        return self._ref_value

    def write_ref(self, ref_id, commit_id, read_key):
        pass


class FakeMergeHelper:
    def __init__(self, conflicts=None):
        self._conflicts = conflicts or []

    def three_way_merge(self, base, ours, theirs):
        return {'merged_map': theirs, 'conflicts': self._conflicts,
                'added': [], 'modified': [], 'deleted': []}

    def write_conflict_files(self, directory, conflicts, theirs_map, obj_store, read_key):
        return []


class FakeFetcher:
    def __init__(self, lca_result=None):
        self._lca = lca_result

    def find_lca(self, obj_store, read_key, commit_a, commit_b):
        return self._lca


class FakeAPI:
    def __init__(self, read_return=None):
        self._read_return = read_return

    def read(self, vault_id, file_id):
        return self._read_return


class FakeSyncClient:
    def __init__(self, api=None, ref_value=''):
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
        return {'n_fetched': 3}

    def _checkout_flat_map(self, directory, flat_map, obj_store, read_key):
        pass

    def _remove_deleted_flat(self, directory, ours_map, new_map):
        pass


class FakeStorage:
    def local_dir(self, directory):
        return directory


class FakeWorkspace:
    def __init__(self, api=None, ref_value='', lca=None, conflicts=None):
        self.sync_client    = FakeSyncClient(api=api)
        self.branch_manager = FakeBranchManager()
        self.ref_manager    = FakeRefManager(ref_value=ref_value)
        self.obj_store      = object()
        self.vc             = FakeVC()
        self.sub_tree       = FakeSubTree()
        self.merge_helper   = FakeMergeHelper(conflicts=conflicts)
        self.fetcher        = FakeFetcher(lca_result=lca)
        self.storage        = FakeStorage()
        self.on_progress    = None

    def ensure_managers(self, sg_dir):
        pass

    def progress(self, tag, msg):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Derive Keys
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Pull__Derive_Keys:

    def test_derive_keys_sets_vault_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Pull__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Pull__Derive_Keys().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID

    def test_derive_keys_sets_read_key_hex(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Pull__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Pull__Derive_Keys().execute(state, ws)
        assert str(out.read_key_hex) == READ_KEY_HEX

    def test_derive_keys_sets_sg_dir(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Pull__State(directory=Safe_Str__File_Path(str(tmp_path)))
        out   = Step__Pull__Derive_Keys().execute(state, ws)
        assert out.sg_dir is not None


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Load Branch Info
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Pull__Load_Branch_Info:

    def test_loads_clone_and_named_ref_ids(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Load_Branch_Info().execute(state, ws)
        assert out.clone_ref_id is not None
        assert out.named_ref_id is not None

    def test_clone_branch_not_found_raises(self, tmp_path):
        ws                          = FakeWorkspace()
        ws.branch_manager           = FakeBranchManager(return_clone=False)
        state                       = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Clone branch not found'):
            Step__Pull__Load_Branch_Info().execute(state, ws)

    def test_named_branch_not_found_raises(self, tmp_path):
        ws                          = FakeWorkspace()
        ws.branch_manager           = FakeBranchManager(return_named=False)
        state                       = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        with pytest.raises(RuntimeError, match='Named branch "current" not found'):
            Step__Pull__Load_Branch_Info().execute(state, ws)

    def test_empty_branch_index_file_id_raises(self, tmp_path):
        ws    = FakeWorkspace()
        state = Schema__Pull__State(
            vault_id              = Safe_Str__Vault_Id(VAULT_ID),
            read_key_hex          = Safe_Str__Write_Key(READ_KEY_HEX),
            branch_index_file_id  = Safe_Str__Index_Id(''),
            sg_dir                = Safe_Str__File_Path(str(tmp_path)),
            directory             = Safe_Str__File_Path(str(tmp_path)),
            clone_branch_id       = Safe_Str__Branch_Id(CLONE_BRANCH_ID),
            clone_ref_id          = Safe_Str__Ref_Id(CLONE_REF_ID),
            named_ref_id          = Safe_Str__Ref_Id(NAMED_REF_ID),
        )
        with pytest.raises(RuntimeError, match='No branch index found'):
            Step__Pull__Load_Branch_Info().execute(state, ws)

    def test_clone_commit_id_read_from_ref(self, tmp_path):
        ws              = FakeWorkspace(ref_value=COMMIT_A)
        state           = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out             = Step__Pull__Load_Branch_Info().execute(state, ws)
        assert str(out.clone_commit_id) == COMMIT_A


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Fetch Remote Ref
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Pull__Fetch_Remote_Ref:

    def test_remote_not_reachable_when_api_returns_none(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=None))
        ws.ref_manager._ref_value = ''
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is False

    def test_remote_reachable_when_api_returns_data(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=b'encrypted-ref-bytes'))
        ws.ref_manager._ref_value = COMMIT_B
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is True

    def test_named_commit_id_set_from_ref_manager(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=None), ref_value=COMMIT_B)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Fetch_Remote_Ref().execute(state, ws)
        assert str(out.named_commit_id) == COMMIT_B

    def test_api_exception_handled_gracefully(self, tmp_path):
        class ErrorAPI:
            def read(self, vault_id, file_id): raise ConnectionError('network down')

        ws    = FakeWorkspace(api=ErrorAPI(), ref_value='')
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Fetch_Remote_Ref().execute(state, ws)
        assert out.remote_reachable is False

    def test_ref_data_written_to_disk(self, tmp_path):
        ws    = FakeWorkspace(api=FakeAPI(read_return=b'ref-data'), ref_value=COMMIT_B)
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        Step__Pull__Fetch_Remote_Ref().execute(state, ws)
        ref_path = os.path.join(str(tmp_path), f'bare/refs/{NAMED_REF_ID}')
        assert os.path.isfile(ref_path)


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Fetch Missing
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Pull__Fetch_Missing:

    def test_skips_fetch_when_commits_identical(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 0

    def test_fetches_objects_when_commits_differ(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 3

    def test_skips_fetch_when_no_named_commit(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Pull__Fetch_Missing().execute(state, ws)
        assert int(str(out.n_objects_fetched)) == 0

    def test_output_preserves_vault_id(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path))
        out   = Step__Pull__Fetch_Missing().execute(state, ws)
        assert str(out.vault_id) == VAULT_ID


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — Merge
# ══════════════════════════════════════════════════════════════════════════════

class Test_Step__Pull__Merge:

    def test_up_to_date_no_named_commit(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(sg_dir=str(tmp_path), directory=str(tmp_path))
        out   = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'up_to_date'

    def test_up_to_date_same_commits(self, tmp_path):
        ws    = FakeWorkspace()
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_A),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'up_to_date'

    def test_up_to_date_when_lca_equals_named(self, tmp_path):
        ws = FakeWorkspace(lca=COMMIT_B)
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'up_to_date'

    def test_fast_forward_when_lca_equals_clone(self, tmp_path):
        ws = FakeWorkspace(lca=COMMIT_A)
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'fast_forward'
        assert str(out.merge_commit_id) == COMMIT_B

    def test_three_way_merge_no_conflicts(self, tmp_path):
        ws = FakeWorkspace(lca=COMMIT_LCA, conflicts=[])
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'merge'
        assert out.merge_commit_id is not None

    def test_three_way_merge_with_conflicts(self, tmp_path):
        ws = FakeWorkspace(lca=COMMIT_LCA, conflicts=['conflict.txt'])
        ws.storage = FakeStorage()
        ws.storage.local_dir = lambda d: str(tmp_path)
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status == 'conflict'
        assert int(str(out.n_conflicts)) == 1

    def test_merge_no_lca_still_proceeds(self, tmp_path):
        ws = FakeWorkspace(lca=None, conflicts=[])
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            clone_commit_id = Safe_Str__Commit_Id(COMMIT_A),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status in ('merge', 'conflict')

    def test_fast_forward_no_clone_commit(self, tmp_path):
        ws = FakeWorkspace(lca=None)
        state = _base_state(
            sg_dir          = str(tmp_path),
            directory       = str(tmp_path),
            named_commit_id = Safe_Str__Commit_Id(COMMIT_B),
        )
        out = Step__Pull__Merge().execute(state, ws)
        assert out.merge_status in ('fast_forward', 'merge', 'conflict')
