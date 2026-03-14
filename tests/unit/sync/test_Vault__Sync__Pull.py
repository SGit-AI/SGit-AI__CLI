import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sg_send_cli.sync.Vault__Sync                  import Vault__Sync
from sg_send_cli.sync.Vault__Storage               import Vault__Storage
from sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sg_send_cli.objects.Vault__Commit             import Vault__Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sg_send_cli.api.Vault__API__In_Memory         import Vault__API__In_Memory


class Test_Vault__Sync__Pull:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.pki     = PKI__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='my-vault'):
        directory = os.path.join(self.tmp_dir, name)
        return self.sync.init(directory), directory

    def _simulate_remote_push(self, directory: str, files: dict):
        """Simulate another user pushing changes by updating the named branch ref.

        Creates a new commit on the named branch with the given files.
        """
        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, '.sg_vault')

        storage     = Vault__Storage()
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)

        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = branch_manager.find_branch_index_id(directory)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        named_meta   = branch_manager.get_branch_by_name(branch_index, 'current')
        named_ref_id = str(named_meta.head_ref_id)
        parent_id    = ref_manager.read_ref(named_ref_id, read_key)

        tree = Schema__Object_Tree(schema='tree_v1')
        for path, content in files.items():
            encrypted = self.crypto.encrypt(read_key, content.encode() if isinstance(content, str) else content)
            blob_id   = obj_store.store(encrypted)
            tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=len(content)))

        named_priv_key_id = str(named_meta.private_key_id)
        signing_key = key_manager.load_private_key(named_priv_key_id, read_key)

        vault_commit = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                     object_store=obj_store, ref_manager=ref_manager)
        commit_id = vault_commit.create_commit(tree=tree, read_key=read_key,
                                               parent_ids=[parent_id] if parent_id else [],
                                               message='remote push',
                                               branch_id=str(named_meta.branch_id),
                                               signing_key=signing_key)
        ref_manager.write_ref(named_ref_id, commit_id, read_key)
        return commit_id

    def test_pull_up_to_date(self):
        _, directory = self._init_vault()
        result = self.sync.pull(directory)
        assert result['status'] == 'up_to_date'

    def test_pull_fast_forward(self):
        _, directory = self._init_vault()

        self._simulate_remote_push(directory, {'remote_file.txt': 'remote content'})

        result = self.sync.pull(directory)
        assert result['status'] == 'merged'
        assert 'remote_file.txt' in result['added']
        assert os.path.isfile(os.path.join(directory, 'remote_file.txt'))
        with open(os.path.join(directory, 'remote_file.txt')) as f:
            assert f.read() == 'remote content'

    def test_pull_with_local_changes_no_conflict(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local content')
        self.sync.commit(directory, message='local change')

        self._simulate_remote_push(directory, {'remote.txt': 'remote content'})

        result = self.sync.pull(directory)
        assert result['status'] == 'merged'
        assert os.path.isfile(os.path.join(directory, 'local.txt'))
        assert os.path.isfile(os.path.join(directory, 'remote.txt'))

    def test_pull_with_conflict(self):
        init_result, directory = self._init_vault()

        with open(os.path.join(directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(directory, message='local change')

        self._simulate_remote_push(directory, {'shared.txt': 'remote version'})

        result = self.sync.pull(directory)
        assert result['status'] == 'conflicts'
        assert 'shared.txt' in result['conflicts']
        assert os.path.isfile(os.path.join(directory, 'shared.txt.conflict'))

    def test_merge_abort(self):
        _, directory = self._init_vault()

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
        _, directory = self._init_vault()
        import pytest
        with pytest.raises(RuntimeError, match='No merge in progress'):
            self.sync.merge_abort(directory)

    def test_pull_remote_deletes_file(self):
        _, directory = self._init_vault()

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
