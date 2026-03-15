import json
import os
import tempfile
import shutil
import pytest

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


class Test_Vault__Sync__Push:

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
        result    = self.sync.init(directory)
        self.sync.push(directory)                    # upload bare structure to server
        return result, directory

    def _simulate_remote_push(self, directory: str, files: dict):
        """Simulate another user pushing changes by updating the named branch ref.

        Updates both local object store AND the remote API so that pull
        can detect the change when it fetches the remote ref.
        """
        import base64
        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']
        write_key  = keys['write_key']
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
            # Also upload blob to remote API
            self.api.write(vault_id, f'bare/data/{blob_id}', write_key, encrypted)

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

        # Upload commit, tree, and updated ref to remote API
        commit_data = obj_store.load(commit_id)
        self.api.write(vault_id, f'bare/data/{commit_id}', write_key, commit_data)
        commit_obj = vault_commit.load_commit(commit_id, read_key)
        tree_data  = obj_store.load(str(commit_obj.tree_id))
        self.api.write(vault_id, f'bare/data/{commit_obj.tree_id}', write_key, tree_data)

        ref_ciphertext = ref_manager.encrypt_ref_value(commit_id, read_key)
        self.api.write(vault_id, f'bare/refs/{named_ref_id}', write_key, ref_ciphertext)

        return commit_id

    def test_push_nothing_to_push(self):
        _, directory = self._init_vault()
        result = self.sync.push(directory)
        assert result['status'] == 'up_to_date'

    def test_push_single_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')
        self.sync.commit(directory, message='add hello')

        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1
        assert result['commits_pushed'] == 1

    def test_push_multiple_files(self):
        _, directory = self._init_vault()

        for i in range(3):
            with open(os.path.join(directory, f'file{i}.txt'), 'w') as f:
                f.write(f'content {i}')
        self.sync.commit(directory, message='add files')

        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 3
        assert result['commits_pushed'] == 1

    def test_push_rejects_dirty_working_directory(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'uncommitted.txt'), 'w') as f:
            f.write('not committed')

        with pytest.raises(RuntimeError, match='uncommitted changes'):
            self.sync.push(directory)

    def test_push_pulls_first(self):
        _, directory = self._init_vault()

        # Simulate remote push
        self._simulate_remote_push(directory, {'remote.txt': 'remote content'})

        # Local commit
        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local content')
        self.sync.commit(directory, message='local change')

        result = self.sync.push(directory)
        assert result['status'] == 'pushed'

        # Verify both files exist after push
        assert os.path.isfile(os.path.join(directory, 'local.txt'))
        assert os.path.isfile(os.path.join(directory, 'remote.txt'))

    def test_push_with_conflict_raises(self):
        _, directory = self._init_vault()

        # Local commit on shared file
        with open(os.path.join(directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit(directory, message='local change')

        # Remote push on same file
        self._simulate_remote_push(directory, {'shared.txt': 'remote version'})

        with pytest.raises(RuntimeError, match='merge conflicts'):
            self.sync.push(directory)

    def test_push_updates_named_branch_ref(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'test.txt'), 'w') as f:
            f.write('test content')
        self.sync.commit(directory, message='add test')

        self.sync.push(directory)

        # After push, named and clone refs should match
        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, '.sg_vault')

        storage     = Vault__Storage()
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = branch_manager.find_branch_index_id(directory)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_name(branch_index, 'local')
        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        clone_ref = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_ref = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        assert clone_ref == named_ref

    def test_push_second_push_only_uploads_delta(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'first.txt'), 'w') as f:
            f.write('first file')
        self.sync.commit(directory, message='add first')
        self.sync.push(directory)

        initial_writes = self.api._write_count

        with open(os.path.join(directory, 'second.txt'), 'w') as f:
            f.write('second file')
        self.sync.commit(directory, message='add second')

        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1  # only the new blob, not first.txt again

    def test_push_branch_only(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'wip.txt'), 'w') as f:
            f.write('work in progress')
        self.sync.commit(directory, message='wip commit')

        result = self.sync.push(directory, branch_only=True)
        assert result['status'] == 'pushed_branch_only'
        assert result['objects_uploaded'] >= 1
        assert result['commits_pushed'] >= 1
        assert 'branch_ref_id' in result

        # Verify named branch ref was NOT updated (still None or initial)
        vault_key  = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys       = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key   = keys['read_key_bytes']
        sg_dir     = os.path.join(directory, '.sg_vault')

        storage     = Vault__Storage()
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=self.pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=storage)
        index_id     = branch_manager.find_branch_index_id(directory)
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)

        clone_meta = branch_manager.get_branch_by_name(branch_index, 'local')
        named_meta = branch_manager.get_branch_by_name(branch_index, 'current')

        clone_ref = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
        named_ref = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)

        assert clone_ref != named_ref  # clone has commit, named doesn't

    def test_push_after_pull_up_to_date(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'test.txt'), 'w') as f:
            f.write('test')
        self.sync.commit(directory, message='add test')
        self.sync.push(directory)

        # Push again — should be up to date
        result = self.sync.push(directory)
        assert result['status'] == 'up_to_date'
