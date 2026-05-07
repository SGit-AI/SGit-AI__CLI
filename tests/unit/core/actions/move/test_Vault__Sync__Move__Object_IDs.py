"""Object-ID stability tests for vault move — Brief 03 §3b.

The design contract: object file IDs (obj-cas-imm-*) never change across key
rotation.  Only ciphertext changes.  The sentinel commit adds exactly one new
object per active named branch.  No pre-move object is ever lost.
"""
import copy
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.core.actions.move.Vault__Sync__Move import Vault__Sync__Move
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sync():
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    return Vault__Sync(crypto=crypto, api=api), crypto, api


def _object_ids(vault_dir: str) -> set:
    data_dir = os.path.join(vault_dir, '.sg_vault', 'bare', 'data')
    if not os.path.isdir(data_dir):
        return set()
    return {f for f in os.listdir(data_dir) if f.startswith('obj-cas-imm-')}


def _active_named_branch_count(vault_dir: str, crypto: Vault__Crypto, api) -> int:
    from sgit_ai.safe_types.Enum__Branch_Type import Enum__Branch_Type
    from sgit_ai.storage.Vault__Storage import Vault__Storage
    key_path = os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')
    vault_key = open(key_path).read().strip()
    keys     = crypto.derive_keys_from_vault_key(vault_key)
    read_key = keys['read_key_bytes']
    index_id = keys.get('branch_index_file_id', '')
    vault_id = keys['vault_id']
    if not index_id:
        return 0
    raw   = api.read(vault_id, f'bare/indexes/{index_id}')
    data  = json.loads(crypto.decrypt(read_key, raw))
    count = sum(1 for b in data.get('branches', [])
                if b.get('branch_type') in ('named', 'NAMED'))
    return count


def _run_move(vault_dir, crypto, api, new_vault_key=None, reason='test'):
    mover = Vault__Sync__Move(crypto=crypto, api=api)
    mover.move(vault_dir, new_vault_key=new_vault_key, reason=reason)


# ---------------------------------------------------------------------------
# 1. Single-commit vault: pre=N, post=N+1 (only sentinel new)
# ---------------------------------------------------------------------------

class Test_Object_IDs__Single_Commit:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'hello.txt': 'hello world\n'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_no_pre_move_ids_are_lost(self):
        pre  = _object_ids(self.env.vault_dir)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post = _object_ids(self.env.vault_dir)
        lost = pre - post
        assert lost == set(), f'object IDs vanished: {lost}'

    def test_exactly_one_new_object_per_named_branch(self):
        pre       = _object_ids(self.env.vault_dir)
        n_named   = _active_named_branch_count(
            self.env.vault_dir, self.env.crypto, self.env.api)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post      = _object_ids(self.env.vault_dir)
        new_objs  = post - pre
        assert len(new_objs) == n_named, (
            f'expected {n_named} new sentinel objects, got {len(new_objs)}'
        )


# ---------------------------------------------------------------------------
# 2. Multi-commit vault (5 commits)
# ---------------------------------------------------------------------------

class Test_Object_IDs__Multi_Commit:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        # Build a vault with 5 commits
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)
        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')
        sync.init(vault_dir)
        for i in range(1, 6):
            path = os.path.join(vault_dir, f'file_{i}.txt')
            with open(path, 'w') as fh:
                fh.write(f'content {i}')
            sync.commit(vault_dir, message=f'commit {i}')
        sync.push(vault_dir)
        cls._env._snapshot_dir   = snap_dir
        cls._env._snapshot_store = copy.deepcopy(api._store)
        cls._env._vault_key      = open(
            os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        cls._env._commit_id      = None
        cls._env._mode           = 'single'
        cls._env._vault_sub      = 'vault'

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_no_ids_lost_multi_commit(self):
        pre  = _object_ids(self.env.vault_dir)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post = _object_ids(self.env.vault_dir)
        assert (pre - post) == set()

    def test_sentinel_count_matches_named_branches(self):
        pre     = _object_ids(self.env.vault_dir)
        n       = _active_named_branch_count(
            self.env.vault_dir, self.env.crypto, self.env.api)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post    = _object_ids(self.env.vault_dir)
        assert len(post - pre) == n


# ---------------------------------------------------------------------------
# 3. Vault with 2 active named branches: 2 sentinels added
# ---------------------------------------------------------------------------

class Test_Object_IDs__Two_Branches:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        switcher = Vault__Branch_Switch(crypto=self.crypto)

        self.tmp  = tempfile.mkdtemp()
        vault_dir = os.path.join(self.tmp, 'vault')
        sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'base.txt'), 'w') as fh:
            fh.write('base')
        sync.commit(vault_dir, message='base')
        sync.push(vault_dir)

        branches = sync.branches(vault_dir)
        main_b   = next(b for b in branches['branches'] if b['branch_type'] == 'named')
        switcher.branch_new(vault_dir, 'feature', from_branch_id=main_b['branch_id'])
        switcher.switch(vault_dir, 'feature')
        with open(os.path.join(vault_dir, 'feature.txt'), 'w') as fh:
            fh.write('feature')
        sync.commit(vault_dir, message='feature commit')
        sync.push(vault_dir)

        self.vault_dir = vault_dir

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_branches_two_sentinels(self):
        pre  = _object_ids(self.vault_dir)
        _run_move(self.vault_dir, self.crypto, self.api)
        post = _object_ids(self.vault_dir)
        new  = post - pre
        assert len(new) == 2, f'expected 2 sentinel objects (one per named branch), got {len(new)}'

    def test_no_ids_lost_with_two_branches(self):
        pre  = _object_ids(self.vault_dir)
        _run_move(self.vault_dir, self.crypto, self.api)
        post = _object_ids(self.vault_dir)
        assert (pre - post) == set()


# ---------------------------------------------------------------------------
# 4. Vault with merge commits in history: merges' IDs unchanged
# ---------------------------------------------------------------------------

class Test_Object_IDs__Merge_History:
    _env = None

    @classmethod
    def setup_class(cls):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync     = Vault__Sync(crypto=crypto, api=api)
        switcher = Vault__Branch_Switch(crypto=crypto)

        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')
        sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'a.txt'), 'w') as fh:
            fh.write('a')
        sync.commit(vault_dir, message='base')
        sync.push(vault_dir)

        branches = sync.branches(vault_dir)
        main_b   = next(b for b in branches['branches'] if b['branch_type'] == 'named')
        switcher.branch_new(vault_dir, 'side', from_branch_id=main_b['branch_id'])
        switcher.switch(vault_dir, 'side')
        with open(os.path.join(vault_dir, 'b.txt'), 'w') as fh:
            fh.write('b')
        sync.commit(vault_dir, message='side commit')
        sync.push(vault_dir)

        # Switch back to main and commit (diverged)
        switcher.switch(vault_dir, main_b['name'])
        with open(os.path.join(vault_dir, 'c.txt'), 'w') as fh:
            fh.write('c')
        sync.commit(vault_dir, message='main extra')
        sync.push(vault_dir)

        vault_key = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()

        cls._snap_dir   = snap_dir
        cls._snap_store = copy.deepcopy(api._store)
        cls._vault_key  = vault_key
        cls._vault_sub  = 'vault'

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls._snap_dir, ignore_errors=True)

    def setup_method(self):
        self.tmp      = tempfile.mkdtemp()
        src           = os.path.join(self._snap_dir, self._vault_sub)
        dst           = os.path.join(self.tmp, self._vault_sub)
        shutil.copytree(src, dst)
        self.vault_dir = dst
        self.crypto   = Vault__Crypto()
        self.api      = Vault__API__In_Memory()
        self.api.setup()
        self.api._store = copy.deepcopy(self._snap_store)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_ids_lost_with_merge_history(self):
        pre  = _object_ids(self.vault_dir)
        _run_move(self.vault_dir, self.crypto, self.api)
        post = _object_ids(self.vault_dir)
        assert (pre - post) == set(), f'lost: {pre - post}'

    def test_new_objects_limited_to_sentinels(self):
        pre      = _object_ids(self.vault_dir)
        n_named  = _active_named_branch_count(self.vault_dir, self.crypto, self.api)
        _run_move(self.vault_dir, self.crypto, self.api)
        post     = _object_ids(self.vault_dir)
        new_objs = post - pre
        assert len(new_objs) <= n_named + 1  # at most one sentinel per named branch


# ---------------------------------------------------------------------------
# 5. ID stability across two sequential moves
# ---------------------------------------------------------------------------

class Test_Object_IDs__Sequential_Moves:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'doc.txt': 'document content'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_ids_stable_across_two_sequential_moves(self):
        pre   = _object_ids(self.env.vault_dir)
        mover = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)

        mover.move(self.env.vault_dir, reason='first move')
        after_1 = _object_ids(self.env.vault_dir)
        assert (pre - after_1) == set(), f'lost after move 1: {pre - after_1}'

        mover2 = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        mover2.move(self.env.vault_dir, reason='second move')
        after_2 = _object_ids(self.env.vault_dir)
        assert (pre - after_2) == set(), f'lost after move 2: {pre - after_2}'

    def test_ciphertext_changes_but_ids_stay(self):
        data_dir = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
        pre_ids  = _object_ids(self.env.vault_dir)
        pre_data = {}
        for fid in pre_ids:
            with open(os.path.join(data_dir, fid), 'rb') as f:
                pre_data[fid] = f.read()

        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)

        for fid in pre_ids:
            path = os.path.join(data_dir, fid)
            assert os.path.isfile(path), f'file {fid} missing after move'
            with open(path, 'rb') as f:
                post_bytes = f.read()
            assert post_bytes != pre_data[fid], (
                f'ciphertext unchanged for {fid} — re-encryption did not run'
            )
