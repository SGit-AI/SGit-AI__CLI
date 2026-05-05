"""Tests for P0: sparse-clone commit must not silently delete unfetched files."""
import json
import os

from tests._helpers.vault_test_env import Vault__Test_Env
from sgit_ai.storage.Vault__Storage  import Vault__Storage


def _set_sparse(directory: str, value: bool):
    storage     = Vault__Storage()
    config_path = storage.local_config_path(directory)
    with open(config_path, 'r') as f:
        data = json.load(f)
    data['sparse'] = value
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)


def _head_flat_paths(sync, directory):
    from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree
    from sgit_ai.storage.Vault__Commit       import Vault__Commit
    from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
    from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
    from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
    from sgit_ai.core.Vault__Sync__Base      import Vault__Sync__Base

    base = Vault__Sync__Base(crypto=sync.crypto, api=sync.api)
    c    = base._init_components(directory)

    sg_dir      = c.sg_dir
    read_key    = c.read_key
    obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=sync.crypto)
    ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=sync.crypto)

    branch_index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, read_key)

    storage = Vault__Storage()
    with open(storage.local_config_path(directory)) as f:
        lc = json.load(f)
    branch_id   = lc['my_branch_id']
    branch_meta = c.branch_manager.get_branch_by_id(branch_index, branch_id)
    ref_id      = str(branch_meta.head_ref_id)
    parent_id   = ref_manager.read_ref(ref_id, read_key)
    if not parent_id:
        return set()

    pki      = PKI__Crypto()
    vc       = Vault__Commit(crypto=sync.crypto, pki=pki,
                             object_store=obj_store, ref_manager=ref_manager)
    commit   = vc.load_commit(parent_id, read_key)
    sub_tree = Vault__Sub_Tree(crypto=sync.crypto, obj_store=obj_store)
    flat     = sub_tree.flatten(str(commit.tree_id), read_key)
    return set(flat.keys())


class Test__Sparse__Commit__Preserves_Unfetched:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'readme.md':    b'hello',
            'src/main.py':  b'print("hello")',
            'src/utils.py': b'pass',
        })

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_sparse_commit_preserves_unfetched_files(self):
        _set_sparse(self.dir, True)

        # Simulate unfetched: remove utils.py from disk (still in parent tree)
        os.remove(os.path.join(self.dir, 'src', 'utils.py'))
        # Make a real change so there is something to commit
        with open(os.path.join(self.dir, 'readme.md'), 'wb') as f:
            f.write(b'updated readme')

        result = self.sync.commit(self.dir, message='sparse update')
        paths  = _head_flat_paths(self.sync, self.dir)

        assert 'src/utils.py' in paths, 'Unfetched file was silently deleted (P0 regression)'
        assert 'readme.md' in paths
        assert 'src/main.py' in paths

    def test_sparse_commit_with_allow_deletions_explicit(self):
        _set_sparse(self.dir, True)
        os.remove(os.path.join(self.dir, 'src', 'utils.py'))
        with open(os.path.join(self.dir, 'readme.md'), 'wb') as f:
            f.write(b'updated readme')

        self.sync.commit(self.dir, message='explicit delete', allow_deletions=True)
        paths = _head_flat_paths(self.sync, self.dir)

        assert 'src/utils.py' not in paths
        assert 'readme.md' in paths
        assert 'src/main.py' in paths

    def test_sparse_commit_blocks_implicit_deletion_via_rm_unfetched(self):
        _set_sparse(self.dir, True)
        os.remove(os.path.join(self.dir, 'src', 'utils.py'))
        os.remove(os.path.join(self.dir, 'readme.md'))
        # Modify the remaining file so there is something to commit
        with open(os.path.join(self.dir, 'src', 'main.py'), 'wb') as f:
            f.write(b'print("changed")')

        self.sync.commit(self.dir, message='partial update')
        paths = _head_flat_paths(self.sync, self.dir)

        assert 'src/utils.py' in paths
        assert 'readme.md' in paths
        assert 'src/main.py' in paths

    def test_non_sparse_commit_behavior_unchanged(self):
        # sparse defaults to False
        os.remove(os.path.join(self.dir, 'src', 'utils.py'))

        self.sync.commit(self.dir, message='normal commit')
        paths = _head_flat_paths(self.sync, self.dir)

        assert 'src/utils.py' not in paths
        assert 'readme.md' in paths
        assert 'src/main.py' in paths

    def test_sparse_commit_message_includes_preserved_note(self):
        _set_sparse(self.dir, True)
        os.remove(os.path.join(self.dir, 'src', 'utils.py'))
        with open(os.path.join(self.dir, 'readme.md'), 'wb') as f:
            f.write(b'updated readme')

        result = self.sync.commit(self.dir, message='')
        assert 'sparse-preserved' in result['message']
        assert '0 deleted' in result['message']
