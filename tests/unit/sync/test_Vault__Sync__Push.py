import json
import os
import pytest

from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sgit_ai.sync.Vault__Sync                  import Vault__Sync
from sgit_ai.sync.Vault__Storage               import Vault__Storage
from sgit_ai.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sgit_ai.objects.Vault__Commit             import Vault__Commit
from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sgit_ai.api.Vault__API__In_Memory         import Vault__API__In_Memory
from tests.unit.sync.vault_test_env            import Vault__Test_Env


class Test_Vault__Sync__Push:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()   # init + push bare skeleton

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env     = self._env.restore()
        self.crypto  = self.env.crypto
        self.pki     = PKI__Crypto()
        self.api     = self.env.api
        self.sync    = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def _simulate_remote_push(self, directory: str, files: dict):
        """Simulate another user pushing changes by updating the named branch ref."""
        import base64
        from sgit_ai.sync.Vault__Sub_Tree import Vault__Sub_Tree

        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']
        write_key  = keys['write_key']
        sg_dir     = os.path.join(directory, '.sg_vault')

        storage     = Vault__Storage()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)

        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = keys['branch_index_file_id']
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')
        named_ref_id = str(named_meta.head_ref_id)
        parent_id    = ref_manager.read_ref(named_ref_id, read_key)

        # Store blobs and build flat map
        flat_map = {}
        for path, content in files.items():
            content_bytes = content.encode() if isinstance(content, str) else content
            encrypted     = self.crypto.encrypt(read_key, content_bytes)
            blob_id       = obj_store.store(encrypted)
            flat_map[path] = {'blob_id': blob_id, 'size': len(content_bytes),
                              'content_hash': self.crypto.content_hash(content_bytes)}
            self.api.write(vault_id, f'bare/data/{blob_id}', write_key, encrypted)

        # Build sub-tree from flat map
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        root_tree_id = sub_tree.build_from_flat(flat_map, read_key)

        named_priv_key_id = str(named_meta.private_key_id)
        signing_key = key_manager.load_private_key(named_priv_key_id, read_key)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_id = vault_commit.create_commit(read_key    = read_key,
                                               tree_id     = root_tree_id,
                                               parent_ids  = [parent_id] if parent_id else [],
                                               message     = 'remote push',
                                               branch_id   = str(named_meta.branch_id),
                                               signing_key = signing_key)
        ref_manager.write_ref(named_ref_id, commit_id, read_key)

        # Upload commit, tree, and updated ref to remote API
        commit_data = obj_store.load(commit_id)
        self.api.write(vault_id, f'bare/data/{commit_id}', write_key, commit_data)
        tree_data = obj_store.load(root_tree_id)
        self.api.write(vault_id, f'bare/data/{root_tree_id}', write_key, tree_data)

        ref_ciphertext = ref_manager.encrypt_ref_value(commit_id, read_key)
        self.api.write(vault_id, f'bare/refs/{named_ref_id}', write_key, ref_ciphertext)

        return commit_id

    def test_push_nothing_to_push(self):
        result = self.sync.push(self.directory)
        assert result['status'] == 'up_to_date'

    def test_push_single_file(self):
        with open(os.path.join(self.directory, 'hello.txt'), 'w') as f:
            f.write('hello world')
        self.sync.commit(self.directory, message='add hello')

        result = self.sync.push(self.directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1
        assert result['commits_pushed'] == 1

    def test_push_multiple_files(self):
        for i in range(3):
            with open(os.path.join(self.directory, f'file{i}.txt'), 'w') as f:
                f.write(f'content {i}')
        self.sync.commit(self.directory, message='add files')

        result = self.sync.push(self.directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 3
        assert result['commits_pushed'] == 1

    def test_push_rejects_dirty_working_directory(self):
        with open(os.path.join(self.directory, 'uncommitted.txt'), 'w') as f:
            f.write('not committed')

        with pytest.raises(RuntimeError, match='uncommitted changes'):
            self.sync.push(self.directory)

    def test_push_pulls_first(self):
        # Simulate remote push
        self._simulate_remote_push(self.directory, {'remote.txt': 'remote content'})

        # Local commit
        with open(os.path.join(self.directory, 'local.txt'), 'w') as f:
            f.write('local content')
        self.sync.commit(self.directory, message='local change')

        result = self.sync.push(self.directory)
        assert result['status'] == 'pushed'

        # Verify both files exist after push
        assert os.path.isfile(os.path.join(self.directory, 'local.txt'))
        assert os.path.isfile(os.path.join(self.directory, 'remote.txt'))

    def test_push_with_conflict_raises(self):
        # Local commit on shared file
        with open(os.path.join(self.directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(self.directory, message='local change')

        # Remote push on same file
        self._simulate_remote_push(self.directory, {'shared.txt': 'remote version'})

        with pytest.raises(RuntimeError, match='merge conflicts'):
            self.sync.push(self.directory)

    def test_push_updates_named_branch_ref(self):
        with open(os.path.join(self.directory, 'test.txt'), 'w') as f:
            f.write('test content')
        self.sync.commit(self.directory, message='add test')

        self.sync.push(self.directory)

        # After push, named and clone refs should match
        vault_key  = open(os.path.join(self.directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(self.directory, '.sg_vault')

        storage     = Vault__Storage()
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = keys['branch_index_file_id']
        branch_index = branch_manager.load_branch_index(self.directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_name(branch_index, 'local')
        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        clone_ref = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_ref = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        assert clone_ref == named_ref

    def test_push_second_push_only_uploads_delta(self):
        with open(os.path.join(self.directory, 'first.txt'), 'w') as f:
            f.write('first file')
        self.sync.commit(self.directory, message='add first')
        self.sync.push(self.directory)

        initial_writes = self.api._write_count

        with open(os.path.join(self.directory, 'second.txt'), 'w') as f:
            f.write('second file')
        self.sync.commit(self.directory, message='add second')

        result = self.sync.push(self.directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1  # only the new blob, not first.txt again

    def test_push_branch_only(self):
        with open(os.path.join(self.directory, 'wip.txt'), 'w') as f:
            f.write('work in progress')
        self.sync.commit(self.directory, message='wip commit')

        result = self.sync.push(self.directory, branch_only=True)
        assert result['status'] == 'pushed_branch_only'
        assert result['objects_uploaded'] >= 1
        assert result['commits_pushed'] >= 1
        assert 'branch_ref_id' in result

        # Verify named branch ref was NOT updated (still None or initial)
        vault_key  = open(os.path.join(self.directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(self.directory, '.sg_vault')

        storage     = Vault__Storage()
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = keys['branch_index_file_id']
        branch_index = branch_manager.load_branch_index(self.directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_name(branch_index, 'local')
        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        clone_ref = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_ref = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        assert clone_ref != named_ref  # clone has commit, named doesn't

    def test_push_after_pull_up_to_date(self):
        with open(os.path.join(self.directory, 'test.txt'), 'w') as f:
            f.write('test')
        self.sync.commit(self.directory, message='add test')
        self.sync.push(self.directory)

        # Push again — should be up to date
        result = self.sync.push(self.directory)
        assert result['status'] == 'up_to_date'
