import json
import os
import tempfile
import shutil
import pytest

from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from sg_send_cli.api.Vault__API                    import Vault__API
from sg_send_cli.sync.Vault__Sync                  import Vault__Sync
from sg_send_cli.sync.Vault__Storage               import Vault__Storage
from sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sg_send_cli.objects.Vault__Commit             import Vault__Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Vault__API__In_Memory(Vault__API):

    def setup(self):
        self._store = {}
        self._write_count = 0
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        self._store[f'{vault_id}/{file_id}'] = payload
        self._write_count += 1
        return {'status': 'ok'}

    def read(self, vault_id: str, file_id: str) -> bytes:
        key = f'{vault_id}/{file_id}'
        if key not in self._store:
            raise RuntimeError(f'Not found: {key}')
        return self._store[key]

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        key = f'{vault_id}/{file_id}'
        self._store.pop(key, None)
        return {'status': 'ok'}


class Test_Vault__Sync__Push_V2:

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
        return self.sync.init_v2(directory), directory

    def _simulate_remote_push(self, directory: str, files: dict):
        """Simulate another user pushing changes by updating the named branch ref."""
        vault_key  = open(os.path.join(directory, '.sg_vault', 'VAULT-KEY')).read().strip()
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

    def test_push_nothing_to_push(self):
        _, directory = self._init_vault()
        result = self.sync.push_v2(directory)
        assert result['status'] == 'up_to_date'

    def test_push_single_file(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'hello.txt'), 'w') as f:
            f.write('hello world')
        self.sync.commit_v2(directory, message='add hello')

        result = self.sync.push_v2(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1
        assert result['commits_pushed'] == 1

    def test_push_multiple_files(self):
        _, directory = self._init_vault()

        for i in range(3):
            with open(os.path.join(directory, f'file{i}.txt'), 'w') as f:
                f.write(f'content {i}')
        self.sync.commit_v2(directory, message='add files')

        result = self.sync.push_v2(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 3
        assert result['commits_pushed'] == 1

    def test_push_rejects_dirty_working_directory(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'uncommitted.txt'), 'w') as f:
            f.write('not committed')

        with pytest.raises(RuntimeError, match='uncommitted changes'):
            self.sync.push_v2(directory)

    def test_push_pulls_first(self):
        _, directory = self._init_vault()

        # Simulate remote push
        self._simulate_remote_push(directory, {'remote.txt': 'remote content'})

        # Local commit
        with open(os.path.join(directory, 'local.txt'), 'w') as f:
            f.write('local content')
        self.sync.commit_v2(directory, message='local change')

        result = self.sync.push_v2(directory)
        assert result['status'] == 'pushed'

        # Verify both files exist after push
        assert os.path.isfile(os.path.join(directory, 'local.txt'))
        assert os.path.isfile(os.path.join(directory, 'remote.txt'))

    def test_push_with_conflict_raises(self):
        _, directory = self._init_vault()

        # Local commit on shared file
        with open(os.path.join(directory, 'shared.txt'), 'w') as f:
            f.write('local version')
        self.sync.commit_v2(directory, message='local change')

        # Remote push on same file
        self._simulate_remote_push(directory, {'shared.txt': 'remote version'})

        with pytest.raises(RuntimeError, match='merge conflicts'):
            self.sync.push_v2(directory)

    def test_push_updates_named_branch_ref(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'test.txt'), 'w') as f:
            f.write('test content')
        self.sync.commit_v2(directory, message='add test')

        self.sync.push_v2(directory)

        # After push, named and clone refs should match
        vault_key  = open(os.path.join(directory, '.sg_vault', 'VAULT-KEY')).read().strip()
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
        self.sync.commit_v2(directory, message='add first')
        self.sync.push_v2(directory)

        initial_writes = self.api._write_count

        with open(os.path.join(directory, 'second.txt'), 'w') as f:
            f.write('second file')
        self.sync.commit_v2(directory, message='add second')

        result = self.sync.push_v2(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1  # only the new blob, not first.txt again

    def test_push_after_pull_up_to_date(self):
        _, directory = self._init_vault()

        with open(os.path.join(directory, 'test.txt'), 'w') as f:
            f.write('test')
        self.sync.commit_v2(directory, message='add test')
        self.sync.push_v2(directory)

        # Push again — should be up to date
        result = self.sync.push_v2(directory)
        assert result['status'] == 'up_to_date'
