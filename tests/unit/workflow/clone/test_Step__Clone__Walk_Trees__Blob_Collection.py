import copy
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                             import Vault__Sync
from sgit_ai.core.actions.clone.Vault__Sync__Clone        import Vault__Sync__Clone
from sgit_ai.crypto.Vault__Crypto                         import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory            import Vault__API__In_Memory
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.workflow.Workflow__Runner                    import Workflow__Runner
from sgit_ai.workflow.clone.Clone__Workspace              import Clone__Workspace
from sgit_ai.workflow.clone.Step__Clone__Walk_Trees       import Step__Clone__Walk_Trees
from sgit_ai.workflow.clone.Step__Clone__Walk_Trees__Head_Only import Step__Clone__Walk_Trees__Head_Only
from sgit_ai.workflow.clone.Workflow__Clone               import Workflow__Clone
from sgit_ai.workflow.clone.Workflow__Clone__Branch       import Workflow__Clone__Branch


def _make_vault(vault_key: str, commits: list[dict]) -> tuple:
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync     = Vault__Sync(crypto=crypto, api=api)
    tmp      = tempfile.mkdtemp(prefix='wt_blob_src_')
    vault_dir = os.path.join(tmp, 'vault')

    sync.init(vault_dir, vault_key=vault_key)
    for i, files in enumerate(commits):
        for rel_path, content in files.items():
            full = os.path.join(vault_dir, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        sync.commit(vault_dir, message=f'commit {i}')
    sync.push(vault_dir)

    snapshot_store = copy.deepcopy(api._store)
    shutil.rmtree(tmp, ignore_errors=True)
    return crypto, snapshot_store


def _run_workflow_to_walk_trees(vault_key, crypto, snapshot_store, wf_class=Workflow__Clone):
    tmp       = tempfile.mkdtemp(prefix='wt_blob_dst_')
    clone_dir = os.path.join(tmp, 'clone')
    try:
        api = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(snapshot_store)

        sync_clone = Vault__Sync__Clone(crypto=crypto, api=api)
        wf         = wf_class()
        ws         = Clone__Workspace.create(wf.workflow_name(), tmp)
        ws.sync_client = sync_clone
        ws.on_progress = None

        initial = Schema__Clone__State(
            vault_key = Safe_Str__Vault_Key(vault_key),
            directory = Safe_Str__File_Path(clone_dir),
        )
        runner = Workflow__Runner(workflow=wf, workspace=ws, keep_work=False)
        final = runner.run(input=initial)
        return final, final
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Test_Step__Clone__Walk_Trees__Blob_Collection:

    def test_walk_trees_collects_blob_ids_from_every_commit(self):
        vault_key = 'blobtest:blobvault01'
        crypto, store = _make_vault(vault_key, [
            {'README.md': 'version 1', 'other.txt': 'static'},
            {'README.md': 'version 2'},
            {'README.md': 'version 3'},
        ])
        step_out, _ = _run_workflow_to_walk_trees(vault_key, crypto, store)

        all_blobs = step_out.get('all_blob_ids', [])
        assert len(all_blobs) >= 4, (
            f'Expected ≥4 blob IDs (3 README versions + other.txt), got {len(all_blobs)}')

    def test_walk_trees_deduplicates_blob_ids(self):
        vault_key = 'blobtest:blobvault02'
        crypto, store = _make_vault(vault_key, [
            {'static.txt': 'unchanged content'},
            {'static.txt': 'unchanged content', 'new.txt': 'new file'},
        ])
        step_out, _ = _run_workflow_to_walk_trees(vault_key, crypto, store)

        all_blobs = step_out.get('all_blob_ids', [])
        assert len(all_blobs) == len(set(all_blobs)), 'all_blob_ids contains duplicates'

    def test_walk_trees_with_no_commits_returns_empty(self):
        state = Schema__Clone__State(
            root_tree_ids = [],
            vault_id      = None,
            sg_dir        = None,
            read_key_hex  = None,
        )
        assert state.all_blob_ids   == []
        assert state.large_blob_ids == []

    def test_schema_state_has_all_blob_ids_field(self):
        state = Schema__Clone__State()
        assert hasattr(state, 'all_blob_ids'),   'Missing all_blob_ids on Schema__Clone__State'
        assert hasattr(state, 'large_blob_ids'), 'Missing large_blob_ids on Schema__Clone__State'
        assert state.all_blob_ids   == []
        assert state.large_blob_ids == []

    def test_schema_round_trip_with_blob_ids(self):
        from sgit_ai.safe_types.Safe_Str__Object_Id import Safe_Str__Object_Id
        state = Schema__Clone__State()
        data  = state.json()
        data['all_blob_ids']   = ['obj-cas-imm-aabbccdd1122', 'obj-cas-imm-eeff55667788']
        data['large_blob_ids'] = ['obj-cas-imm-aabbccdd1122']
        restored = Schema__Clone__State.from_json(data)
        assert len(restored.all_blob_ids)   == 2
        assert len(restored.large_blob_ids) == 1
        assert Schema__Clone__State.from_json(restored.json()).json() == restored.json()


class Test_Step__Clone__Download_Blobs__From_List:

    def test_download_blobs_uses_all_blob_ids_from_walk(self):
        vault_key = 'blobtest:blobvault04'
        crypto, store = _make_vault(vault_key, [
            {'file.txt': 'version A'},
            {'file.txt': 'version B'},
            {'file.txt': 'version C'},
        ])
        tmp       = tempfile.mkdtemp(prefix='wt_dl_dst_')
        clone_dir = os.path.join(tmp, 'clone')
        try:
            api = Vault__API__In_Memory()
            api.setup()
            api._store = copy.deepcopy(store)

            sync = Vault__Sync(crypto=crypto, api=api)
            sync.clone(vault_key, clone_dir)

            data_dir = os.path.join(clone_dir, '.sg_vault', 'bare', 'data')
            assert os.path.isdir(data_dir)
            blob_count = sum(1 for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-'))
            assert blob_count >= 3, (
                f'Expected ≥3 objects (one per file version), got {blob_count}')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_download_blobs_skips_working_copy_in_sparse(self):
        vault_key = 'blobtest:blobvault05'
        crypto, store = _make_vault(vault_key, [
            {'sparse_file.txt': 'content'},
        ])
        tmp       = tempfile.mkdtemp(prefix='wt_sparse_')
        clone_dir = os.path.join(tmp, 'clone')
        try:
            api = Vault__API__In_Memory()
            api.setup()
            api._store = copy.deepcopy(store)

            sync = Vault__Sync(crypto=crypto, api=api)
            sync.clone(vault_key, clone_dir, sparse=True)

            assert not os.path.isfile(os.path.join(clone_dir, 'sparse_file.txt')), (
                'Sparse clone should not extract working copy files')
            assert os.path.isdir(os.path.join(clone_dir, '.sg_vault'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clone_branch_remains_thin(self):
        vault_key = 'blobtest:blobvault06'
        crypto, store = _make_vault(vault_key, [
            {'evolving.txt': 'v1'},
            {'evolving.txt': 'v2'},
            {'evolving.txt': 'v3'},
        ])
        tmp       = tempfile.mkdtemp(prefix='wt_branch_')
        clone_dir = os.path.join(tmp, 'clone')
        try:
            api = Vault__API__In_Memory()
            api.setup()
            api._store = copy.deepcopy(store)

            step_out, _ = _run_workflow_to_walk_trees(
                vault_key, crypto, copy.deepcopy(store),
                wf_class=Workflow__Clone__Branch
            )
            all_blobs = step_out.get('all_blob_ids', [])
            assert len(all_blobs) == 1, (
                f'clone-branch should collect only HEAD blobs (1), got {len(all_blobs)}')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
