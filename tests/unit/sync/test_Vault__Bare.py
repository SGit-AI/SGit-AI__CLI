import json
import os
import tempfile
import shutil
from datetime                                      import datetime, timezone
from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from sg_send_cli.schemas.Schema__Object_Commit     import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sg_send_cli.sync.Vault__Bare                  import Vault__Bare


class Test_Vault__Bare:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.bare      = Vault__Bare(crypto=self.crypto)
        self.vault_key = 'testpassphrase1234567890:abcd1234'
        self._create_test_vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_test_vault(self):
        keys         = self.crypto.derive_keys_from_vault_key(self.vault_key)
        read_key     = keys['read_key_bytes']
        sg_vault_dir = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(sg_vault_dir, exist_ok=True)

        object_store = Vault__Object_Store(vault_path=sg_vault_dir, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=sg_vault_dir)

        tree_obj = Schema__Object_Tree()

        file_content = b'{"key": "value"}'
        encrypted    = self.crypto.encrypt(read_key, file_content)
        blob_id      = object_store.store(encrypted)
        tree_obj.entries.append(Schema__Object_Tree_Entry(path='config.json', blob_id=blob_id, size=len(file_content)))

        file2_content = b'deploy script contents'
        encrypted2    = self.crypto.encrypt(read_key, file2_content)
        blob_id2      = object_store.store(encrypted2)
        tree_obj.entries.append(Schema__Object_Tree_Entry(path='deploy/run.sh', blob_id=blob_id2, size=len(file2_content)))

        now                = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        tree_json          = json.dumps(tree_obj.json()).encode()
        encrypted_tree_obj = self.crypto.encrypt(read_key, tree_json)
        tree_obj_id        = object_store.store(encrypted_tree_obj)

        commit = Schema__Object_Commit(tree_id=tree_obj_id, version=1, timestamp=now, message='test')
        commit_json      = json.dumps(commit.json()).encode()
        encrypted_commit = self.crypto.encrypt(read_key, commit_json)
        commit_id        = object_store.store(encrypted_commit)

        ref_manager.write_head(commit_id)

    def test_is_bare__bare_vault(self):
        assert self.bare.is_bare(self.tmp_dir) is True

    def test_is_bare__with_vault_key(self):
        local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(local_dir, exist_ok=True)
        vault_key_path = os.path.join(local_dir, 'vault_key')
        with open(vault_key_path, 'w') as f:
            f.write(self.vault_key)
        assert self.bare.is_bare(self.tmp_dir) is False

    def test_list_files(self):
        files = self.bare.list_files(self.tmp_dir, self.vault_key)
        paths = [f['path'] for f in files]
        assert sorted(paths) == ['config.json', 'deploy/run.sh']

    def test_read_file(self):
        content = self.bare.read_file(self.tmp_dir, self.vault_key, 'config.json')
        assert content == b'{"key": "value"}'

    def test_read_file__not_found(self):
        import pytest
        with pytest.raises(RuntimeError, match='File not found'):
            self.bare.read_file(self.tmp_dir, self.vault_key, 'nonexistent.txt')

    def test_checkout__extracts_files(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        assert os.path.isfile(os.path.join(self.tmp_dir, 'deploy', 'run.sh'))
        with open(os.path.join(self.tmp_dir, 'config.json'), 'rb') as f:
            assert f.read() == b'{"key": "value"}'

    def test_checkout__writes_vault_key(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        vault_key_path = os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key')
        assert os.path.isfile(vault_key_path)
        with open(vault_key_path, 'r') as f:
            assert f.read() == self.vault_key

    def test_clean__removes_plaintext_files(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        self.bare.clean(self.tmp_dir)
        assert not os.path.isfile(os.path.join(self.tmp_dir, 'config.json'))
        assert not os.path.isfile(os.path.join(self.tmp_dir, 'deploy', 'run.sh'))

    def test_clean__removes_vault_key(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        self.bare.clean(self.tmp_dir)
        assert not os.path.isfile(os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key'))

    def test_clean__preserves_object_store(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        self.bare.clean(self.tmp_dir)
        objects_dir = os.path.join(self.tmp_dir, '.sg_vault', 'objects')
        assert os.path.isdir(objects_dir)
        refs_head = os.path.join(self.tmp_dir, '.sg_vault', 'refs', 'head')
        assert os.path.isfile(refs_head)

    def test_roundtrip__checkout_clean_verify(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert not self.bare.is_bare(self.tmp_dir)

        self.bare.clean(self.tmp_dir)
        assert self.bare.is_bare(self.tmp_dir)

        content = self.bare.read_file(self.tmp_dir, self.vault_key, 'deploy/run.sh')
        assert content == b'deploy script contents'
