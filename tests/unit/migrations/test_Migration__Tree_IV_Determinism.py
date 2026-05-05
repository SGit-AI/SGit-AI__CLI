"""Tests for Migration__Tree_IV_Determinism."""
import os
import json

from sgit_ai.migrations.tree_iv.Migration__Tree_IV_Determinism import Migration__Tree_IV_Determinism
from sgit_ai.migrations.Migration__Runner import Migration__Runner
from sgit_ai.migrations.Migration__Registry import Migration__Registry
from tests._helpers.vault_test_env import Vault__Test_Env


def _make_old_vault(env_snapshot):
    """Return (vault_dir, sg_dir, read_key) for a snapshot's vault."""
    from sgit_ai.core.Vault__Sync import Vault__Sync
    vault_dir = env_snapshot.vault_dir
    sg_dir    = os.path.join(vault_dir, '.sg_vault')
    sync      = Vault__Sync(crypto=env_snapshot.crypto, api=env_snapshot.api)
    keys      = sync._derive_keys_from_stored_key(env_snapshot.vault_key)
    read_key  = bytes.fromhex(keys['read_key'])
    return vault_dir, sg_dir, read_key


def _corrupt_trees_to_random_iv(sg_dir, read_key):
    """Re-encrypt all tree objects with RANDOM IV to simulate an old vault.
    Returns list of (old_id, new_id) pairs for verification.
    """
    from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
    from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
    from sgit_ai.crypto.PKI__Crypto import PKI__Crypto
    from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
    from sgit_ai.storage.Vault__Commit import Vault__Commit
    import os

    crypto    = Vault__Crypto()
    obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
    ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
    vc        = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                              object_store=obj_store, ref_manager=ref_mgr)

    # Collect tree IDs and commit graph BEFORE corruption (old trees still intact)
    mig = Migration__Tree_IV_Determinism()
    tree_ids = mig._collect_tree_ids(ref_mgr, vc, obj_store, read_key)
    head_commit_ids, commit_parent_map, commit_tree_map, tree_children, all_tree_ids = \
        mig._collect_commit_and_tree_graph(ref_mgr, vc, obj_store, read_key)

    # Re-encrypt each tree with random IV
    id_pairs = []
    for old_tid in tree_ids:
        ciphertext = obj_store.load(old_tid)
        plaintext  = crypto.decrypt(read_key, ciphertext)
        new_cipher = crypto.encrypt(read_key, plaintext)  # random IV
        new_tid    = obj_store._compute_id(new_cipher)
        if new_tid != old_tid:
            obj_store.store(new_cipher)
            os.remove(obj_store.object_path(old_tid))
            id_pairs.append((old_tid, new_tid))

    # Update commits to reference random-IV trees

    old_to_rand = {old: rand for old, rand in id_pairs}
    sorted_commits = mig._topo_sort_commits(head_commit_ids, commit_parent_map)
    commit_mapping = {}
    for cid in sorted_commits:
        old_tree = commit_tree_map.get(cid, '')
        new_tree = old_to_rand.get(old_tree, old_tree)
        old_parents = commit_parent_map.get(cid, [])
        new_parents = [commit_mapping.get(p, p) for p in old_parents]
        if new_tree == old_tree and new_parents == old_parents:
            continue
        try:
            commit  = vc.load_commit(cid, read_key)
            new_cid = vc.create_commit(
                read_key     = read_key,
                tree_id      = new_tree,
                parent_ids   = new_parents,
                message_enc  = str(commit.message_enc) if commit.message_enc else None,
                branch_id    = str(commit.branch_id) if commit.branch_id else None,
                timestamp_ms = int(str(commit.timestamp_ms)) if commit.timestamp_ms else None,
            )
            commit_mapping[cid] = new_cid
        except Exception:
            pass

    # Update refs
    for ref_id in ref_mgr.list_refs():
        old_cid = ref_mgr.read_ref(ref_id, read_key)
        if old_cid and old_cid in commit_mapping:
            ref_mgr.write_ref(ref_id, commit_mapping[old_cid], read_key)

    return id_pairs


class Test_Migration__Tree_IV_Determinism:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.md': b'hello',
            'src/main.py': b'print("hello")',
            'src/utils.py': b'pass',
        })

    def setup_method(self):
        self.env = self._env.restore()
        self.vault_dir, self.sg_dir, self.read_key = _make_old_vault(self.env)

    def teardown_method(self):
        self.env.cleanup()

    def test_migration_name(self):
        m = Migration__Tree_IV_Determinism()
        assert m.migration_name() == 'tree-iv-determinism'

    def test_is_applied_on_new_vault(self):
        """A newly created vault (post-HMAC-IV) should already be deterministic."""
        m = Migration__Tree_IV_Determinism()
        assert m.is_applied(self.sg_dir, self.read_key) is True

    def test_is_applied_false_on_random_iv_vault(self):
        """After corrupting trees to random IV, is_applied returns False."""
        pairs = _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        if not pairs:
            return  # vault has no trees (shouldn't happen with files)
        m = Migration__Tree_IV_Determinism()
        assert m.is_applied(self.sg_dir, self.read_key) is False

    def test_apply_on_random_iv_vault_returns_nonzero_trees(self):
        """apply() should migrate trees."""
        pairs = _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        if not pairs:
            return
        m     = Migration__Tree_IV_Determinism()
        stats = m.apply(self.sg_dir, self.read_key)
        assert stats['n_trees'] > 0

    def test_apply_makes_vault_deterministic(self):
        """After apply(), is_applied() should return True."""
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        m = Migration__Tree_IV_Determinism()
        m.apply(self.sg_dir, self.read_key)
        assert m.is_applied(self.sg_dir, self.read_key) is True

    def test_apply_idempotent(self):
        """Second apply() is a no-op."""
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        m = Migration__Tree_IV_Determinism()
        m.apply(self.sg_dir, self.read_key)
        stats = m.apply(self.sg_dir, self.read_key)
        assert stats['n_trees'] == 0

    def test_backup_file_created(self):
        """apply() creates pre-migration-trees.json."""
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        m = Migration__Tree_IV_Determinism()
        m.apply(self.sg_dir, self.read_key)
        backup = os.path.join(self.sg_dir, 'local', 'pre-migration-trees.json')
        assert os.path.isfile(backup)
        with open(backup) as f:
            data = json.load(f)
        assert 'migrated_trees' in data

    def test_dedup_improvement_after_migration(self):
        """After migration, trees are deterministic — applying again finds no new mappings."""
        pairs = _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        if not pairs:
            return  # nothing to check

        m = Migration__Tree_IV_Determinism()

        # Before: not deterministic
        assert m.is_applied(self.sg_dir, self.read_key) is False

        stats = m.apply(self.sg_dir, self.read_key)
        # At least some trees were migrated
        assert stats['n_trees'] > 0

        # After: deterministic — applying again is a no-op
        stats2 = m.apply(self.sg_dir, self.read_key)
        assert stats2['n_trees'] == 0
        assert m.is_applied(self.sg_dir, self.read_key) is True


class Test_Migration__Runner:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': b'hello'})

    def setup_method(self):
        self.env = self._env.restore()
        self.vault_dir, self.sg_dir, self.read_key = _make_old_vault(self.env)

    def teardown_method(self):
        self.env.cleanup()

    def _runner(self):
        return Migration__Runner(registry=Migration__Registry())

    def test_plan_empty_on_new_vault(self):
        """New vault (deterministic trees) → no pending migrations."""
        r = self._runner()
        assert r.plan(self.vault_dir, self.read_key) == []

    def test_plan_shows_pending_on_old_vault(self):
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        r       = self._runner()
        pending = r.plan(self.vault_dir, self.read_key)
        assert 'tree-iv-determinism' in pending

    def test_apply_records_migration(self):
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        r    = self._runner()
        done = r.apply(self.vault_dir, self.read_key)
        assert 'tree-iv-determinism' in done

    def test_status_after_apply(self):
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        r = self._runner()
        r.apply(self.vault_dir, self.read_key)
        records = r.status(self.vault_dir)
        assert len(records) == 1
        assert records[0]['name'] == 'tree-iv-determinism'

    def test_apply_idempotent_via_runner(self):
        _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        r = self._runner()
        r.apply(self.vault_dir, self.read_key)
        done2 = r.apply(self.vault_dir, self.read_key)
        assert done2 == []


class Test_Migration__Runner__Schema:

    def setup_method(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.sg_dir = os.path.join(self.tmp, '.sg_vault')
        os.makedirs(self.sg_dir, exist_ok=True)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _runner(self):
        return Migration__Runner(registry=Migration__Registry())

    def test_schema_round_trip(self):
        from sgit_ai.schemas.migrations.Schema__Migrations_Applied import Schema__Migrations_Applied
        r = self._runner()
        r._save_record(self.sg_dir, 'tree-iv-determinism', 123, {'n_trees': 5, 'n_commits': 3, 'n_refs': 2})
        records = r.status(self.tmp)
        assert len(records) == 1
        record = records[0]
        reread = Schema__Migrations_Applied.from_json({'records': [record]})
        assert reread.records[0].json() == record

    def test_status_returns_list_of_dicts(self):
        r = self._runner()
        r._save_record(self.sg_dir, 'tree-iv-determinism', 50, {'n_trees': 1, 'n_commits': 1, 'n_refs': 1})
        records = r.status(self.tmp)
        assert isinstance(records, list)
        assert len(records) == 1
        assert records[0]['name'] == 'tree-iv-determinism'

    def test_multiple_records_round_trip(self):
        r = self._runner()
        r._save_record(self.sg_dir, 'tree-iv-determinism', 10, {'n_trees': 1, 'n_commits': 1, 'n_refs': 1})
        r._save_record(self.sg_dir, 'tree-iv-determinism', 20, {'n_trees': 0, 'n_commits': 0, 'n_refs': 0})
        records = r.status(self.tmp)
        assert len(records) == 2


class Test_Migration__Hardening__Cycle_Detection:

    def test_topo_sort_trees_raises_on_cycle(self):
        mig         = Migration__Tree_IV_Determinism()
        tree_ids    = {'a', 'b'}
        # Create a cycle: a → b → a
        tree_children = {'a': ['b'], 'b': ['a']}
        try:
            mig._topo_sort_trees(tree_ids, tree_children)
            assert False, 'Expected RuntimeError for cycle'
        except RuntimeError as e:
            assert 'cycle' in str(e).lower() or 'unreachable' in str(e).lower()

    def test_topo_sort_commits_raises_on_cycle(self):
        mig = Migration__Tree_IV_Determinism()
        # Simple cycle: a → b → a
        commit_parent_map = {'a': ['b'], 'b': ['a']}
        try:
            mig._topo_sort_commits(['a', 'b'], commit_parent_map)
            assert False, 'Expected RuntimeError for cycle'
        except RuntimeError as e:
            assert 'cycle' in str(e).lower() or 'unreachable' in str(e).lower()
