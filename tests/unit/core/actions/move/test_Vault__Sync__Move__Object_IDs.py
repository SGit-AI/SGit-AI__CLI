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


def _unverified_ids(vault_dir: str) -> set:
    """Object ids whose bytes do NOT hash to the id — must always be empty.

    This is the invariant `sgit vault move` used to break: it re-encrypted every
    object in place under the new key while KEEPING the old id, so afterwards no
    object was verifiable against its own content address. Move now rewrites the
    ids, so the content address holds for a moved vault exactly as it does for a
    fresh one (review finding A1, option 3).
    """
    crypto     = Vault__Crypto()
    data_dir   = os.path.join(vault_dir, '.sg_vault', 'bare', 'data')
    unverified = set()
    for object_id in _object_ids(vault_dir):
        with open(os.path.join(data_dir, object_id), 'rb') as f:
            if crypto.compute_object_id(f.read()) != object_id:
                unverified.add(object_id)
    return unverified


def _work_tree_files(vault_dir: str) -> dict:
    """{rel_path: content} of the working copy — what must survive a move."""
    result = {}
    for root, dirs, files in os.walk(vault_dir):
        dirs[:] = [d for d in dirs if d != '.sg_vault']
        for name in files:
            full = os.path.join(root, name)
            with open(full, 'rb') as f:
                result[os.path.relpath(full, vault_dir).replace(os.sep, '/')] = f.read()
    return result


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


def _two_parent_commits(vault_dir: str) -> tuple:
    """([(object_id, decrypted_commit)], all_object_ids) for the vault's store,
    decrypting with the vault's CURRENT key (valid before and after a move)."""
    crypto    = Vault__Crypto()
    vault_key = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
    read_key  = crypto.derive_keys_from_vault_key(vault_key)['read_key_bytes']
    data_dir  = os.path.join(vault_dir, '.sg_vault', 'bare', 'data')
    all_ids   = _object_ids(vault_dir)
    merges    = []
    for object_id in all_ids:
        with open(os.path.join(data_dir, object_id), 'rb') as f:
            raw = f.read()
        try:
            plain = json.loads(crypto.decrypt(read_key, raw))
        except Exception:
            continue
        if isinstance(plain, dict) and len(plain.get('parents') or []) == 2:
            merges.append((object_id, plain))
    return merges, all_ids


def _run_move(vault_dir, crypto, api, new_vault_key=None, reason='test'):
    mover = Vault__Sync__Move(crypto=crypto, api=api)
    mover.move(vault_dir, new_vault_key=new_vault_key, reason=reason)



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

    def test_no_content_is_lost_and_every_object_is_rewritten(self):
        pre_files = _work_tree_files(self.env.vault_dir)
        pre_ids   = _object_ids(self.env.vault_dir)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post_ids  = _object_ids(self.env.vault_dir)
        # content survives — the invariant that matters ...
        assert _work_tree_files(self.env.vault_dir) == pre_files
        # ... and every object was re-addressed, so nothing links the moved
        # vault's store back to the original (option 3).
        assert (pre_ids & post_ids) == set(), 'ids reused — the move is linkable'

    def test_every_object_verifies_against_its_content_address(self):
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        assert _unverified_ids(self.env.vault_dir) == set()

    def test_exactly_one_new_object_per_named_branch(self):
        pre       = _object_ids(self.env.vault_dir)
        n_named   = _active_named_branch_count(
            self.env.vault_dir, self.env.crypto, self.env.api)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post      = _object_ids(self.env.vault_dir)
        # every object is re-addressed, so growth (not set difference) is what
        # counts the sentinels: one new commit object per named branch.
        assert len(post) - len(pre) == n_named, (
            f'expected {n_named} sentinel objects, got {len(post) - len(pre)}'
        )



class Test_Object_IDs__Multi_Commit:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
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

    def test_no_content_lost_multi_commit(self):
        pre_files = _work_tree_files(self.env.vault_dir)
        pre_ids   = _object_ids(self.env.vault_dir)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        assert _work_tree_files(self.env.vault_dir) == pre_files
        assert (pre_ids & _object_ids(self.env.vault_dir)) == set()
        assert _unverified_ids(self.env.vault_dir) == set()

    def test_sentinel_count_matches_named_branches(self):
        pre     = _object_ids(self.env.vault_dir)
        n       = _active_named_branch_count(
            self.env.vault_dir, self.env.crypto, self.env.api)
        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post    = _object_ids(self.env.vault_dir)
        assert len(post) - len(pre) == n



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
        growth = len(post) - len(pre)
        assert growth == 2, f'expected 2 sentinel objects (one per named branch), got {growth}'

    def test_no_content_lost_with_two_branches(self):
        pre_files = _work_tree_files(self.vault_dir)
        pre_ids   = _object_ids(self.vault_dir)
        _run_move(self.vault_dir, self.crypto, self.api)
        assert _work_tree_files(self.vault_dir) == pre_files
        assert (pre_ids & _object_ids(self.vault_dir)) == set()
        assert _unverified_ids(self.vault_dir) == set()



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
        base_id = sync.commit(vault_dir, message='base')['commit_id']
        sync.push(vault_dir)

        branches = sync.branches(vault_dir)
        main_b   = next(b for b in branches['branches'] if b['branch_type'] == 'named')
        switcher.branch_new(vault_dir, 'side', from_branch_id=main_b['branch_id'])
        switcher.switch(vault_dir, 'side')
        with open(os.path.join(vault_dir, 'b.txt'), 'w') as fh:
            fh.write('b')
        side_id = sync.commit(vault_dir, message='side commit')['commit_id']
        sync.push(vault_dir)

        # Switch back to main and commit (diverged)
        switcher.switch(vault_dir, main_b['name'])
        with open(os.path.join(vault_dir, 'c.txt'), 'w') as fh:
            fh.write('c')
        main_id = sync.commit(vault_dir, message='main extra')['commit_id']
        sync.push(vault_dir)

        # Merge side into main through the production merge-commit path
        # (Vault__Sync__Commit + merge state), so the history really contains
        # a TWO-parent commit — divergence alone never exercises the
        # multi-parent remap (review finding B3).
        from sgit_ai.core.actions.merge.Vault__Merge__State import Vault__Merge__State
        ms_mgr = Vault__Merge__State()
        ms_mgr.write(vault_dir, ms_mgr.new_state(main_id, side_id, base_id, []))
        with open(os.path.join(vault_dir, 'b.txt'), 'w') as fh:
            fh.write('b')
        merge = sync.commit(vault_dir, message='merge side into main')
        assert merge['merge_commit'], 'fixture failed to produce a two-parent commit'
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

    def test_no_content_lost_with_merge_history(self):
        # a merge commit has TWO parents — both must be remapped, or the moved
        # history has a dangling parent id.
        pre_merges, _ = _two_parent_commits(self.vault_dir)
        assert pre_merges, 'fixture must contain a real two-parent merge commit'
        pre_files = _work_tree_files(self.vault_dir)
        pre_ids   = _object_ids(self.vault_dir)
        _run_move(self.vault_dir, self.crypto, self.api)
        assert _work_tree_files(self.vault_dir) == pre_files
        assert (pre_ids & _object_ids(self.vault_dir)) == set()
        assert _unverified_ids(self.vault_dir) == set()
        # the merge commit survived the rewrite and BOTH parents were remapped
        # to objects that exist in the moved store (no dangling second parent)
        post_merges, post_ids = _two_parent_commits(self.vault_dir)
        assert post_merges, 'merge commit lost in the rewrite'
        for object_id, commit in post_merges:
            for parent in commit['parents']:
                assert parent in post_ids, f'{object_id}: parent {parent} dangles'

    def test_new_objects_limited_to_sentinels(self):
        pre      = _object_ids(self.vault_dir)
        n_named  = _active_named_branch_count(self.vault_dir, self.crypto, self.api)
        _run_move(self.vault_dir, self.crypto, self.api)
        post     = _object_ids(self.vault_dir)
        assert len(post) - len(pre) <= n_named + 1  # at most one sentinel per named branch



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

    def test_content_survives_two_sequential_moves(self):
        pre_files = _work_tree_files(self.env.vault_dir)
        pre_ids   = _object_ids(self.env.vault_dir)
        mover     = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)

        mover.move(self.env.vault_dir, reason='first move')
        after_1 = _object_ids(self.env.vault_dir)
        assert _work_tree_files(self.env.vault_dir) == pre_files
        assert (pre_ids & after_1) == set()
        assert _unverified_ids(self.env.vault_dir) == set()

        mover2 = Vault__Sync__Move(crypto=self.env.crypto, api=self.env.api)
        mover2.move(self.env.vault_dir, reason='second move')
        after_2 = _object_ids(self.env.vault_dir)
        assert _work_tree_files(self.env.vault_dir) == pre_files
        assert (after_1 & after_2) == set()          # each move re-addresses again
        assert (pre_ids  & after_2) == set()
        assert _unverified_ids(self.env.vault_dir) == set()

    def test_ciphertext_and_ids_both_change(self):
        """Re-encryption runs AND the content address follows it — the pair that
        makes a moved vault verifiable and unlinkable (option 3). Before, the
        ciphertext changed while the id was deliberately kept."""
        data_dir = os.path.join(self.env.vault_dir, '.sg_vault', 'bare', 'data')
        pre_ids  = _object_ids(self.env.vault_dir)
        pre_data = {}
        for fid in pre_ids:
            with open(os.path.join(data_dir, fid), 'rb') as f:
                pre_data[fid] = f.read()

        _run_move(self.env.vault_dir, self.env.crypto, self.env.api)
        post_ids = _object_ids(self.env.vault_dir)

        assert (pre_ids & post_ids) == set(), 'an id survived the move'
        post_bytes = set()
        for fid in post_ids:
            with open(os.path.join(data_dir, fid), 'rb') as f:
                post_bytes.add(f.read())
        for old_bytes in pre_data.values():          # no ciphertext carried over
            assert old_bytes not in post_bytes
