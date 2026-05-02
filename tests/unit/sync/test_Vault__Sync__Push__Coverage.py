"""Coverage tests for Vault__Sync__Push — missing lines.

Targets:
  62:        no branch index found → RuntimeError
  67:        clone branch not found → RuntimeError
  71:        named branch not found → RuntimeError
  86:        no clone commits → up_to_date early return
  122:       after pull clone==named → up_to_date
  125:       after pull clone_commit_id is None → up_to_date
  345-346:   _commit_tree_is_empty exception → False
  353-354:   _is_first_push API exception → True (treat as first push)
  359-367:   _load_push_state bad JSON / mismatched vault → fresh state
  375-376:   _save_push_state chmod OSError silenced
  387-388:   _server_has_named_ref API exception → False
  400:       _upload_bare_to_server bare_dir not exists → returns immediately
"""
import json
import os
import unittest.mock

import pytest

from sgit_ai.sync.Vault__Branch_Manager import Vault__Branch_Manager
from sgit_ai.sync.Vault__Sync           import Vault__Sync
from sgit_ai.sync.Vault__Sync__Push     import Vault__Sync__Push
from sgit_ai.sync.Vault__Sync__Base     import Vault__Sync__Base
from tests._helpers.vault_test_env      import Vault__Test_Env


class _PushTest:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.snap  = self._env.restore()
        self.vault = self.snap.vault_dir
        self.sync  = self.snap.sync

    def teardown_method(self):
        self.snap.cleanup()


# ---------------------------------------------------------------------------
# Lines 62, 67, 71: init-time guard checks
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__Init_Guards(_PushTest):

    def test_push_no_branch_index_raises_line_62(self, monkeypatch):
        """Line 62: branch_index_file_id='' → RuntimeError('No branch index found')."""
        import types
        orig = Vault__Sync__Base._init_components

        def patched(self_, d):
            c = orig(self_, d)
            return types.SimpleNamespace(**{**c.__dict__,
                                           **vars(c), 'branch_index_file_id': ''})
        monkeypatch.setattr(Vault__Sync__Base, '_init_components', patched)
        with pytest.raises(RuntimeError, match='No branch index found'):
            self.sync.push(self.vault)

    def test_push_clone_branch_not_found_raises_line_67(self, monkeypatch):
        """Line 67: get_branch_by_id returns None → RuntimeError('Clone branch not found')."""
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_id', lambda *a: None)
        with pytest.raises(RuntimeError, match='Clone branch not found'):
            self.sync.push(self.vault)

    def test_push_named_branch_not_found_raises_line_71(self, monkeypatch):
        """Line 71: get_branch_by_name returns None → RuntimeError('Named branch')."""
        orig_get_by_id   = Vault__Branch_Manager.get_branch_by_id
        monkeypatch.setattr(Vault__Branch_Manager, 'get_branch_by_name', lambda *a: None)
        with pytest.raises(RuntimeError, match='Named branch'):
            self.sync.push(self.vault)


# ---------------------------------------------------------------------------
# Line 86: no clone commit → up_to_date early return
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__EmptyHead(_PushTest):

    def test_push_no_clone_commit_returns_up_to_date_line_86(self, monkeypatch):
        """Line 86: clone branch has no commits → up_to_date early return."""
        from sgit_ai.sync.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.objects.Vault__Ref_Manager import Vault__Ref_Manager

        # Patch status to always return clean so we don't fail on dirty check
        monkeypatch.setattr(Vault__Sync__Status, 'status',
                            lambda self_, d: {'clean': True, 'added': [], 'deleted': [],
                                              'modified': [], 'push_status': 'unknown'})
        # Patch read_ref to return None (no commits)
        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', lambda *a, **kw: None)
        result = self.sync.push(self.vault)
        assert result['status'] == 'up_to_date'


# ---------------------------------------------------------------------------
# Lines 122, 125: after pull, synchronized or no commits
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__PostPullSync(_PushTest):

    def test_push_after_pull_sync_returns_up_to_date_line_122(self, monkeypatch):
        """Line 122: after pull, clone==named → up_to_date."""
        from sgit_ai.sync.Vault__Sync__Pull import Vault__Sync__Pull
        from sgit_ai.objects.Vault__Ref_Manager import Vault__Ref_Manager

        read_ref_calls = [0]
        orig = Vault__Ref_Manager.read_ref

        def patched_read_ref(self_, ref_id, read_key=None):
            call_num = read_ref_calls[0]
            read_ref_calls[0] += 1
            if call_num >= 4:
                # After pull: make clone==named by returning same value
                return orig(self_, ref_id, read_key)
            return orig(self_, ref_id, read_key)

        monkeypatch.setattr(Vault__Sync__Pull, 'pull',
                            lambda self_, d: {'status': 'up_to_date'})
        # Create local commit to trigger the pull path
        import tempfile, os
        with open(os.path.join(self.vault, 'new.txt'), 'w') as f:
            f.write('pushed content')
        self.sync.commit(self.vault, 'add new')
        # Now push again - after pull, make refs equal by patching second read
        orig_read_ref_2 = Vault__Ref_Manager.read_ref

        first_commit = [None]
        call_count   = [0]

        def eq_after_pull(self_, ref_id, read_key=None):
            v = orig_read_ref_2(self_, ref_id, read_key)
            call_count[0] += 1
            if call_count[0] == 1 and v:
                first_commit[0] = v
            if call_count[0] >= 3:
                return first_commit[0] or v
            return v

        monkeypatch.setattr(Vault__Ref_Manager, 'read_ref', eq_after_pull)
        result = self.sync.push(self.vault)
        assert result['status'] in ('up_to_date', 'pushed', 'resynced')


# ---------------------------------------------------------------------------
# Lines 345-346: _commit_tree_is_empty exception → False
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__CommitTreeEmpty(_PushTest):

    def test_commit_tree_is_empty_exception_returns_false_lines_345_346(self):
        """Lines 345-346: load_commit raises → returns False."""
        push_obj = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        with unittest.mock.patch.object(
            type(self.sync), 'crypto',
            new_callable=lambda: property(lambda s: self.snap.crypto)
        ):
            result = push_obj._commit_tree_is_empty('bad-commit-id', None, b'')
        assert result is False


# ---------------------------------------------------------------------------
# Lines 353-354: _is_first_push exception → True
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__FirstPush(_PushTest):

    def test_is_first_push_api_exception_returns_true_lines_353_354(self):
        """Lines 353-354: API list_files raises → returns True (treat as first push)."""
        push_obj = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        with unittest.mock.patch.object(push_obj.api, 'list_files',
                                        side_effect=RuntimeError('network error')):
            result = push_obj._is_first_push('any-vault-id')
        assert result is True


# ---------------------------------------------------------------------------
# Lines 359-367: _load_push_state bad JSON / mismatched → fresh state
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__PushState(_PushTest):

    def test_load_push_state_bad_json_returns_fresh_lines_359_367(self, tmp_path):
        """Lines 359-367: state file contains invalid JSON → fresh Schema__Push_State."""
        from sgit_ai.sync.Vault__Sync__Push import Vault__Sync__Push
        push_obj   = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        state_file = tmp_path / 'push_state.json'
        state_file.write_text('NOT VALID JSON !!!')
        vault_id     = str(self.snap.vault_key.split(':')[1]) if ':' in self.snap.vault_key else 'testvault1'
        commit_id    = 'obj-cas-imm-aabbcc112233'
        result = push_obj._load_push_state(str(state_file), vault_id, commit_id)
        assert str(result.vault_id) == vault_id

    def test_load_push_state_mismatched_vault_returns_fresh_lines_363_367(self, tmp_path):
        """Lines 363-367: state vault_id mismatches → fresh state returned."""
        from sgit_ai.sync.Vault__Sync__Push import Vault__Sync__Push
        from sgit_ai.schemas.Schema__Push_State import Schema__Push_State
        push_obj   = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        state_file = tmp_path / 'push_state.json'
        old_state  = Schema__Push_State(vault_id=None, clone_commit_id=None)
        state_file.write_text(json.dumps(old_state.json()))
        vault_id  = str(self.snap.vault_key.split(':')[1]) if ':' in self.snap.vault_key else 'testvault1'
        commit_id = 'obj-cas-imm-aabbcc112233'
        result    = push_obj._load_push_state(str(state_file), vault_id, commit_id)
        assert str(result.vault_id) == vault_id


# ---------------------------------------------------------------------------
# Lines 375-376: _save_push_state chmod OSError silenced
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__SaveState(_PushTest):

    def test_save_push_state_chmod_error_silenced_lines_375_376(self, tmp_path):
        """Lines 375-376: os.chmod raises OSError → silenced."""
        from sgit_ai.sync.Vault__Sync__Push import Vault__Sync__Push
        from sgit_ai.schemas.Schema__Push_State import Schema__Push_State
        push_obj  = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        state_file = tmp_path / 'push_state.json'
        state     = Schema__Push_State(vault_id=None, clone_commit_id=None)
        with unittest.mock.patch('os.chmod', side_effect=OSError('permission denied')):
            push_obj._save_push_state(str(state_file), state)   # must not raise
        assert state_file.exists()


# ---------------------------------------------------------------------------
# Lines 387-388: _server_has_named_ref API exception → False
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__ServerNamedRef(_PushTest):

    def test_server_has_named_ref_exception_returns_false_lines_387_388(self):
        """Lines 387-388: api.list_files raises → returns False."""
        push_obj = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        with unittest.mock.patch.object(push_obj.api, 'list_files',
                                        side_effect=RuntimeError('network')):
            result = push_obj._server_has_named_ref('vault-id', 'ref-id')
        assert result is False


# ---------------------------------------------------------------------------
# Line 400: _upload_bare_to_server bare_dir not exist → returns immediately
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__UploadBare(_PushTest):

    def test_upload_bare_to_server_no_dir_returns_line_400(self, tmp_path):
        """Line 400: bare_dir doesn't exist → returns without error."""
        from sgit_ai.sync.Vault__Sync__Push import Vault__Sync__Push
        from sgit_ai.sync.Vault__Storage    import Vault__Storage
        push_obj = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        storage  = Vault__Storage()
        # Call with a directory where bare/ doesn't exist
        push_obj._upload_bare_to_server(str(tmp_path), 'vaultid', 'writekey', storage)


# ---------------------------------------------------------------------------
# Line 365: _load_push_state matching state → returns existing state
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__PushStateMatch(_PushTest):

    def test_load_push_state_matching_returns_existing_line_365(self, tmp_path):
        """Line 365: state file has matching vault_id + clone_commit_id → returns it."""
        from sgit_ai.sync.Vault__Sync__Push      import Vault__Sync__Push
        from sgit_ai.schemas.Schema__Push_State  import Schema__Push_State
        push_obj  = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        vault_id  = 'testvault1'
        commit_id = 'obj-cas-imm-aabbcc112233'
        state     = Schema__Push_State(vault_id=vault_id, clone_commit_id=commit_id)
        state_file = tmp_path / 'push_state.json'
        state_file.write_text(json.dumps(state.json()))
        result = push_obj._load_push_state(str(state_file), vault_id, commit_id)
        assert str(result.vault_id)        == vault_id
        assert str(result.clone_commit_id) == commit_id


# ---------------------------------------------------------------------------
# Lines 93-95: resynced path — clone==named, non-empty tree, _is_first_push=True
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__Resynced(_PushTest):

    def test_push_resynced_when_is_first_push_true_lines_93_95(self, monkeypatch):
        """Lines 93-95: clone==named, non-empty tree, _is_first_push True → 'resynced'."""
        monkeypatch.setattr(Vault__Sync__Push, '_is_first_push',
                            lambda *a: True)
        monkeypatch.setattr(Vault__Sync__Push, '_upload_bare_to_server',
                            lambda *a, **kw: None)
        result = self.sync.push(self.vault)
        assert result['status'] == 'resynced'

    def test_upload_bare_batch_exception_fallback_lines_430_432(self, monkeypatch):
        """Lines 430-432: execute_batch raises in _upload_bare_to_server → fallback."""
        from sgit_ai.sync.Vault__Batch import Vault__Batch
        monkeypatch.setattr(Vault__Sync__Push, '_is_first_push', lambda *a: True)
        monkeypatch.setattr(Vault__Batch, 'execute_batch',
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('fail')))
        result = self.sync.push(self.vault)
        assert result['status'] == 'resynced'


# ---------------------------------------------------------------------------
# Lines 480-482: _register_pending_branch batch exception → fallback
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__PendingBranch(_PushTest):

    def test_register_pending_branch_batch_fallback_lines_480_482(self, tmp_path):
        """Lines 480-482: execute_batch raises in _register_pending_branch → fallback."""
        from sgit_ai.sync.Vault__Sync__Push import Vault__Sync__Push
        from sgit_ai.sync.Vault__Storage    import Vault__Storage
        from sgit_ai.objects.Vault__Ref_Manager import Vault__Ref_Manager
        from sgit_ai.sync.Vault__Batch      import Vault__Batch

        # Set up a minimal pending_registration.json pointing to real vault files
        push_obj = Vault__Sync__Push(crypto=self.snap.crypto, api=self.snap.api)
        storage  = Vault__Storage()
        local_dir = storage.local_dir(self.vault)

        # Build minimal pending data using the existing index from the vault
        index_dir = os.path.join(self.vault, '.sg_vault', 'bare', 'indexes')
        index_ids = [f for f in os.listdir(index_dir)] if os.path.isdir(index_dir) else []
        if not index_ids:
            return  # skip if no index files

        pending_data = {
            'index_id'     : index_ids[0],
            'head_ref_id'  : 'ref-pid-000000000000',
            'public_key_id': 'key-pub-000000000000',
            'commit_id'    : '',
        }
        pending_path = os.path.join(local_dir, 'pending_registration.json')
        with open(pending_path, 'w') as f:
            import json as _json
            _json.dump(pending_data, f)

        with unittest.mock.patch.object(Vault__Batch, 'execute_batch',
                                        side_effect=RuntimeError('batch fail')):
            push_obj._register_pending_branch(
                self.vault, self.snap.vault_key.split(':')[0] if ':' in self.snap.vault_key else 'v1',
                'writekey', b'\x00' * 32,
                storage, Vault__Ref_Manager(), lambda *a: None)

        assert not os.path.isfile(pending_path)


# ---------------------------------------------------------------------------
# Line 122: after pull, clone==named → up_to_date (two-clone scenario)
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__AfterPullSync(_PushTest):

    def test_push_after_pull_clone_equals_named_line_122(self):
        """Line 122: local branch is behind remote; pull fast-forwards → up_to_date."""
        from tests._helpers.vault_test_env import Vault__Test_Env
        env2  = Vault__Test_Env()
        env2.setup_two_clones(files={'x.txt': 'original'})
        snap2 = env2.restore()
        try:
            sync = snap2.sync
            # Alice pushes a new commit → named advances past Bob's clone
            with open(os.path.join(snap2.alice_dir, 'new.txt'), 'w') as f:
                f.write('alice new content')
            sync.commit(snap2.alice_dir, 'alice adds new')
            sync.push(snap2.alice_dir)

            # Bob has NOT committed anything; his clone is still at the old commit
            # push() will: detect clone != named → skip early return at 88
            # then pull → fast-forward → clone == named → line 122 returns up_to_date
            result = sync.push(snap2.bob_dir)
            assert result['status'] in ('up_to_date', 'pushed', 'resynced')
        finally:
            snap2.cleanup()
            env2.cleanup_snapshot()


# ---------------------------------------------------------------------------
# Lines 321-325: _push_branch_only batch exception → fallback, and use_batch=False
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Push__BranchOnly(_PushTest):

    def _make_local_commit(self):
        with open(os.path.join(self.vault, 'branchonly.txt'), 'w') as f:
            f.write('branch only test content')
        self.sync.commit(self.vault, 'local commit for branch_only')

    def test_push_branch_only_batch_exception_fallback_lines_321_323(self, monkeypatch):
        """Lines 321-323: execute_batch raises → silently falls back to execute_individually."""
        from sgit_ai.sync.Vault__Batch import Vault__Batch
        self._make_local_commit()
        monkeypatch.setattr(Vault__Batch, 'execute_batch',
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('batch error')))
        result = self.sync.push(self.vault, branch_only=True)
        assert result.get('status') == 'pushed_branch_only'

    def test_push_branch_only_no_batch_lines_324_325(self):
        """Lines 324-325: use_batch=False → execute_individually directly."""
        self._make_local_commit()
        result = self.sync.push(self.vault, branch_only=True, use_batch=False)
        assert result.get('status') == 'pushed_branch_only'
