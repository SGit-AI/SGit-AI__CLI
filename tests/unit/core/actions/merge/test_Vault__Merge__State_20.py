import copy
import os
import shutil
import tempfile

import pytest

from sgit_ai.core.Vault__Errors                          import Vault__Merge_In_Progress_Error, Vault__Push_With_Conflicts_Error
from sgit_ai.core.actions.merge.Vault__Merge__State      import Vault__Merge__State
from sgit_ai.core.actions.merge.Vault__Merge__Abort      import Vault__Merge__Abort
from sgit_ai.core.actions.merge.Vault__Merge__Resolve    import Vault__Merge__Resolve
from sgit_ai.core.Vault__Sync                            import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                        import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory           import Vault__API__In_Memory
from sgit_ai.schemas.merge.Schema__Merge_State           import Schema__Merge_State


def _make_vault(vault_key='merge20:testvault01', files=None):
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync      = Vault__Sync(crypto=crypto, api=api)
    tmp       = tempfile.mkdtemp(prefix='ms20_')
    vault_dir = os.path.join(tmp, 'vault')
    sync.init(vault_dir, vault_key=vault_key)
    if files:
        for rel_path, content in files.items():
            full = os.path.join(vault_dir, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        sync.commit(vault_dir, message='initial')
    sync.push(vault_dir)
    return crypto, api, sync, vault_dir, tmp


def _write_conflict_file(vault_dir, rel_path, content='theirs content'):
    full = os.path.join(vault_dir, rel_path + '.conflict')
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


def _inject_merge_state(vault_dir, ours=None, theirs='obj-cas-imm-bbb000222bbb',
                        conflict_paths=None):
    from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
    from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
    from sgit_ai.storage.Vault__Storage     import Vault__Storage
    from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
    import json
    if ours is None:
        storage = Vault__Storage()
        sg_dir  = storage.sg_vault_dir(vault_dir)
        crypto  = Vault__Crypto()
        cfg_path = storage.local_config_path(vault_dir)
        with open(cfg_path) as f:
            cfg = json.load(f)
        local_config = Schema__Local_Config.from_json(cfg)
        vault_key_path = storage.vault_key_path(vault_dir)
        with open(vault_key_path) as f:
            vault_key = f.read().strip()
        keys     = crypto.derive_keys_from_vault_key(vault_key)
        read_key = keys['read_key_bytes']
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        bm = Vault__Branch_Manager(vault_path=sg_dir, crypto=crypto)
        branch_index_files = [f for f in os.listdir(os.path.join(sg_dir, 'bare', 'data'))
                              if f.startswith('obj-cas-imm-')]
        ref_mgr  = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        from sgit_ai.storage.Vault__Storage import SG_VAULT_DIR
        refs_dir = os.path.join(sg_dir, 'bare', 'refs')
        ours = ''
        if os.path.isdir(refs_dir):
            for ref_file in os.listdir(refs_dir):
                try:
                    cid = ref_mgr.read_ref(ref_file, read_key)
                    if cid:
                        ours = cid
                        break
                except Exception:
                    pass
    ms_mgr = Vault__Merge__State()
    state  = ms_mgr.new_state(ours, theirs, None, conflict_paths or ['file.txt'])
    ms_mgr.write(vault_dir, state)
    return state


class Test_Schema__Merge_State__Round_Trip:

    def test_round_trip_empty(self):
        obj = Schema__Merge_State()
        assert Schema__Merge_State.from_json(obj.json()).json() == obj.json()

    def test_round_trip_populated(self):
        from sgit_ai.safe_types.Safe_Str__Commit_Id  import Safe_Str__Commit_Id
        from sgit_ai.safe_types.Safe_Str__File_Path  import Safe_Str__File_Path
        data = {
            'schema_version'  : 1,
            'ours_commit_id'  : 'obj-cas-imm-aaa000111aaa',
            'theirs_commit_id': 'obj-cas-imm-bbb000222bbb',
            'lca_id'          : 'obj-cas-imm-ccc000333ccc',
            'started_at'      : '2026-05-08T12:00:00Z',
            'conflict_paths'  : ['foo.txt', 'bar/baz.txt'],
            'resolved_paths'  : ['qux.txt'],
        }
        obj      = Schema__Merge_State.from_json(data)
        restored = Schema__Merge_State.from_json(obj.json())
        assert restored.json() == obj.json()
        assert len(restored.conflict_paths) == 2
        assert len(restored.resolved_paths) == 1


class Test_Vault__Merge__State__Read_Write:

    def test_new_state_round_trips(self):
        ms_mgr = Vault__Merge__State()
        state  = ms_mgr.new_state('obj-cas-imm-aaa', 'obj-cas-imm-bbb', None, ['a.txt'])
        assert str(state.ours_commit_id)   == 'obj-cas-imm-aaa'
        assert str(state.theirs_commit_id) == 'obj-cas-imm-bbb'
        assert len(state.conflict_paths)   == 1

    def test_write_and_read_back(self):
        tmp = tempfile.mkdtemp(prefix='ms20_rw_')
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync      = Vault__Sync(crypto=crypto, api=api)
            vault_dir = os.path.join(tmp, 'vault')
            sync.init(vault_dir, vault_key='merge20:rw01')

            ms_mgr = Vault__Merge__State()
            state  = ms_mgr.new_state('obj-cas-imm-xxx', 'obj-cas-imm-yyy', None, ['f1.txt', 'f2.txt'])
            ms_mgr.write(vault_dir, state)

            back = ms_mgr.read(vault_dir)
            assert str(back.ours_commit_id)   == 'obj-cas-imm-xxx'
            assert str(back.theirs_commit_id) == 'obj-cas-imm-yyy'
            assert len(back.conflict_paths)   == 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_migrate_legacy_format(self):
        tmp = tempfile.mkdtemp(prefix='ms20_leg_')
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync      = Vault__Sync(crypto=crypto, api=api)
            vault_dir = os.path.join(tmp, 'vault')
            sync.init(vault_dir, vault_key='merge20:leg01')

            import json
            legacy = dict(clone_commit_id='obj-cas-imm-old1', named_commit_id='obj-cas-imm-old2',
                          lca_id='obj-cas-imm-old0', conflicts=['c1.txt', 'c2.txt'])
            state_path = Vault__Merge__State().state_path(vault_dir)
            with open(state_path, 'w') as f:
                json.dump(legacy, f)

            back = Vault__Merge__State().read(vault_dir)
            assert str(back.ours_commit_id)   == 'obj-cas-imm-old1'
            assert str(back.theirs_commit_id) == 'obj-cas-imm-old2'
            assert 'c1.txt' in [str(p) for p in back.conflict_paths]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_check_not_in_progress_raises_when_state_exists(self):
        tmp = tempfile.mkdtemp(prefix='ms20_chk_')
        try:
            crypto = Vault__Crypto()
            api    = Vault__API__In_Memory()
            api.setup()
            sync      = Vault__Sync(crypto=crypto, api=api)
            vault_dir = os.path.join(tmp, 'vault')
            sync.init(vault_dir, vault_key='merge20:chk01')
            _inject_merge_state(vault_dir)
            with pytest.raises(Vault__Merge_In_Progress_Error):
                Vault__Merge__State().check_not_in_progress(vault_dir, 'pull')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Test_Vault__Merge__Abort:

    def setup_method(self):
        self.crypto, self.api, self.sync, self.vault_dir, self.tmp = _make_vault(
            vault_key='merge20:abort01', files={'file.txt': 'ours content'}
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_abort_no_merge_in_progress_raises(self):
        with pytest.raises(RuntimeError, match='No merge in progress'):
            Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(self.vault_dir)

    def test_abort_removes_conflict_files_and_state(self):
        _inject_merge_state(self.vault_dir, conflict_paths=['file.txt'])
        _write_conflict_file(self.vault_dir, 'file.txt')
        assert os.path.isfile(os.path.join(self.vault_dir, 'file.txt.conflict'))

        result = Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(self.vault_dir)

        assert result['status'] == 'aborted'
        assert not os.path.isfile(os.path.join(self.vault_dir, 'file.txt.conflict'))
        assert not Vault__Merge__State().exists(self.vault_dir)

    def test_abort_with_keep_conflict_files(self):
        _inject_merge_state(self.vault_dir, conflict_paths=['file.txt'])
        _write_conflict_file(self.vault_dir, 'file.txt')

        result = Vault__Merge__Abort(crypto=self.crypto, api=self.api).abort(
            self.vault_dir, keep_conflict_files=True)

        assert result['status'] == 'aborted'
        assert result['conflict_files_removed'] == 0
        assert not Vault__Merge__State().exists(self.vault_dir)


class Test_Vault__Merge__Resolve:

    def setup_method(self):
        self.crypto, self.api, self.sync, self.vault_dir, self.tmp = _make_vault(
            vault_key='merge20:resolve01', files={'file.txt': 'ours content'}
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_ours_removes_conflict_file(self):
        _inject_merge_state(self.vault_dir, conflict_paths=['file.txt'])
        _write_conflict_file(self.vault_dir, 'file.txt', 'theirs')

        result = Vault__Merge__Resolve().resolve_file(self.vault_dir, 'file.txt', 'ours')

        assert result['status'] == 'resolved'
        assert not os.path.isfile(os.path.join(self.vault_dir, 'file.txt.conflict'))
        assert os.path.isfile(os.path.join(self.vault_dir, 'file.txt'))

        state = Vault__Merge__State().read(self.vault_dir)
        assert 'file.txt' not in [str(p) for p in (state.conflict_paths or [])]
        assert 'file.txt' in [str(p) for p in (state.resolved_paths or [])]

    def test_resolve_theirs_replaces_working_copy(self):
        _inject_merge_state(self.vault_dir, conflict_paths=['file.txt'])
        _write_conflict_file(self.vault_dir, 'file.txt', 'theirs content')
        with open(os.path.join(self.vault_dir, 'file.txt'), 'w') as f:
            f.write('ours content')

        Vault__Merge__Resolve().resolve_file(self.vault_dir, 'file.txt', 'theirs')

        assert not os.path.isfile(os.path.join(self.vault_dir, 'file.txt.conflict'))
        assert open(os.path.join(self.vault_dir, 'file.txt')).read() == 'theirs content'

    def test_resolve_all_ours(self):
        _inject_merge_state(self.vault_dir, conflict_paths=['a.txt', 'b.txt'])
        _write_conflict_file(self.vault_dir, 'a.txt')
        _write_conflict_file(self.vault_dir, 'b.txt')
        with open(os.path.join(self.vault_dir, 'a.txt'), 'w') as f:
            f.write('a ours')
        with open(os.path.join(self.vault_dir, 'b.txt'), 'w') as f:
            f.write('b ours')

        result = Vault__Merge__Resolve().resolve_all(self.vault_dir, 'ours')

        assert result['resolved'] == 2
        assert not os.path.isfile(os.path.join(self.vault_dir, 'a.txt.conflict'))
        assert not os.path.isfile(os.path.join(self.vault_dir, 'b.txt.conflict'))
        state = Vault__Merge__State().read(self.vault_dir)
        assert len(state.conflict_paths) == 0


class Test_Push_And_Pull_Refusal:

    def setup_method(self):
        self.crypto, self.api, self.sync, self.vault_dir, self.tmp = _make_vault(
            vault_key='merge20:refusal01', files={'doc.txt': 'content'}
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_push_refuses_with_conflict_files(self):
        from sgit_ai.core.actions.push.Vault__Sync__Push import Vault__Sync__Push
        _write_conflict_file(self.vault_dir, 'doc.txt')
        with pytest.raises(Vault__Push_With_Conflicts_Error):
            Vault__Sync__Push(crypto=self.crypto, api=self.api).push(self.vault_dir)

    def test_push_with_conflict_flag_bypasses_check(self):
        from sgit_ai.core.actions.push.Vault__Sync__Push import Vault__Sync__Push
        _write_conflict_file(self.vault_dir, 'doc.txt')
        self.sync.commit(self.vault_dir, message='captured conflicts')
        result = Vault__Sync__Push(crypto=self.crypto, api=self.api).push(
            self.vault_dir, push_conflict=True)
        assert result is not None

    def test_pull_refuses_with_merge_state(self):
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        _inject_merge_state(self.vault_dir)
        with pytest.raises(Vault__Merge_In_Progress_Error):
            Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(self.vault_dir)

    def test_status_surfaces_merge_state(self):
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        _inject_merge_state(self.vault_dir, conflict_paths=['doc.txt'])
        status = Vault__Sync__Status(crypto=self.crypto, api=self.api).status(self.vault_dir)
        assert status.get('merge_in_progress') is True
        assert 'doc.txt' in status.get('merge_conflicts', [])

    def test_status_no_merge_state_is_false(self):
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        status = Vault__Sync__Status(crypto=self.crypto, api=self.api).status(self.vault_dir)
        assert status.get('merge_in_progress') is False


class Test_Flow_B__Merge_Commit:

    def setup_method(self):
        self.crypto, self.api, self.sync, self.vault_dir, self.tmp = _make_vault(
            vault_key='merge20:flowb01', files={'data.txt': 'original'}
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commit_creates_merge_commit_when_no_conflicts(self):
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        _inject_merge_state(self.vault_dir,
                            ours='obj-cas-imm-aaa000111aaa',
                            theirs='obj-cas-imm-bbb000222bbb',
                            conflict_paths=[])
        with open(os.path.join(self.vault_dir, 'data.txt'), 'w') as f:
            f.write('merged content')

        result = Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
            self.vault_dir, message='merge finalised')

        assert result.get('merge_commit') is True
        assert not Vault__Merge__State().exists(self.vault_dir)

    def test_commit_no_merge_commit_flag_is_linear(self):
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        _inject_merge_state(self.vault_dir,
                            ours='obj-cas-imm-aaa000111aaa',
                            theirs='obj-cas-imm-bbb000222bbb',
                            conflict_paths=[])
        with open(os.path.join(self.vault_dir, 'data.txt'), 'w') as f:
            f.write('linear resolution')

        result = Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
            self.vault_dir, message='resolved', no_merge_commit=True)

        assert result.get('merge_commit') is False
        assert not Vault__Merge__State().exists(self.vault_dir)

    def test_commit_with_conflict_files_does_not_delete_state(self):
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        _inject_merge_state(self.vault_dir, conflict_paths=['data.txt'])
        _write_conflict_file(self.vault_dir, 'data.txt', 'theirs version')
        with open(os.path.join(self.vault_dir, 'data.txt'), 'w') as f:
            f.write('ours + captured conflict')

        result = Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(
            self.vault_dir, message='captured conflicts')

        assert result.get('merge_commit') is False
        assert Vault__Merge__State().exists(self.vault_dir)
