import json
import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sgit_ai.sync.Vault__Sync                  import Vault__Sync
from sgit_ai.sync.Vault__Storage               import Vault__Storage
from sgit_ai.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sgit_ai.objects.Vault__Commit             import Vault__Commit
from sgit_ai.sync.Vault__Sub_Tree              import Vault__Sub_Tree
from sgit_ai.api.Vault__API__In_Memory         import Vault__API__In_Memory
from tests.unit.sync.vault_test_env            import Vault__Test_Env


class Test_Vault__Sync__Pull:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.pki       = PKI__Crypto()
        self.api       = self.env.api
        self.sync      = self.env.sync
        self.vault_dir = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def _simulate_remote_push(self, directory: str, files: dict):
        """Simulate another user pushing changes by updating the named branch ref."""
        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
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

        flat_map = {}
        for path, content in files.items():
            content_bytes = content.encode() if isinstance(content, str) else content
            encrypted     = self.crypto.encrypt(read_key, content_bytes)
            blob_id       = obj_store.store(encrypted)
            flat_map[path] = {'blob_id': blob_id, 'size': len(content_bytes),
                              'content_hash': self.crypto.content_hash(content_bytes)}

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
        return commit_id

    def test_pull_up_to_date(self):
        result = self.sync.pull(self.vault_dir)
        assert result['status'] == 'up_to_date'

    def test_pull_fast_forward(self):
        directory = self.vault_dir
        self._simulate_remote_push(directory, {'remote_file.txt': 'remote content'})

        result = self.sync.pull(directory)
        assert result['status'] == 'merged'
        assert 'remote_file.txt' in result['added']
        assert os.path.isfile(os.path.join(directory, 'remote_file.txt'))
        with open(os.path.join(directory, 'remote_file.txt')) as f:
            assert f.read() == 'remote content'

    def test_pull_with_local_changes_no_conflict(self):
        directory = self.vault_dir
        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local content')
        self.sync.commit(directory, message='local change')

        self._simulate_remote_push(directory, {'remote.txt': 'remote content'})

        result = self.sync.pull(directory)
        assert result['status'] == 'merged'
        assert os.path.isfile(os.path.join(directory, 'local.txt'))
        assert os.path.isfile(os.path.join(directory, 'remote.txt'))

    def test_pull_with_conflict(self):
        directory = self.vault_dir
        with open(os.path.join(directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(directory, message='local change')

        self._simulate_remote_push(directory, {'shared.txt': 'remote version'})

        result = self.sync.pull(directory)
        assert result['status'] == 'conflicts'
        assert 'shared.txt' in result['conflicts']
        assert os.path.isfile(os.path.join(directory, 'shared.txt.conflict'))

    def test_merge_abort(self):
        directory = self.vault_dir
        with open(os.path.join(directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(directory, message='local change')

        self._simulate_remote_push(directory, {'shared.txt': 'remote version'})

        pull_result = self.sync.pull(directory)
        assert pull_result['status'] == 'conflicts'

        abort_result = self.sync.merge_abort(directory)
        assert abort_result['status'] == 'aborted'
        assert not os.path.isfile(os.path.join(directory, 'shared.txt.conflict'))

        with open(os.path.join(directory, 'shared.txt')) as f:
            assert f.read() == 'local version'

    def test_merge_abort_no_merge_in_progress(self):
        import pytest
        with pytest.raises(RuntimeError, match='No merge in progress'):
            self.sync.merge_abort(self.vault_dir)

    def test_pull_remote_deletes_file(self):
        directory = self.vault_dir
        with open(os.path.join(directory, 'to_delete.txt'), 'w') as f:
            f.write('will be gone')
        self.sync.commit(directory, message='add file')

        self._simulate_remote_push(directory, {
            'to_delete.txt': 'will be gone'
        })
        self.sync.pull(directory)

        self._simulate_remote_push(directory, {})

        result = self.sync.pull(directory)
        assert result['status'] == 'merged'
