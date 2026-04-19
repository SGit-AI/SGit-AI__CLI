import json
import os
import tempfile
import shutil
from sgit_ai.sync.Vault__Sync            import Vault__Sync, SG_VAULT_DIR
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Object_Commit import Schema__Object_Commit
from sgit_ai.schemas.Schema__Object_Tree   import Schema__Object_Tree
from sgit_ai.api.Vault__API__In_Memory     import Vault__API__In_Memory


class Test_Vault__Sync__Generate_Vault_Key:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory().setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)

    def test_generate_vault_key__format(self):
        key = self.sync.generate_vault_key()
        assert ':' in key
        parts = key.split(':')
        assert len(parts) == 2
        assert len(parts[0]) == 24
        assert len(parts[1]) == 8

    def test_generate_vault_key__unique(self):
        key1 = self.sync.generate_vault_key()
        key2 = self.sync.generate_vault_key()
        assert key1 != key2

    def test_generate_vault_key__valid_chars(self):
        key = self.sync.generate_vault_key()
        passphrase, vault_id = key.rsplit(':', 1)
        assert all(c.isalnum() for c in passphrase)
        assert all(c.isalnum() for c in vault_id)


class Test_Vault__Sync__Scan_Local:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scan__empty_directory(self):
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__ignores_sg_vault(self):
        sg_vault_dir = os.path.join(self.tmp_dir, SG_VAULT_DIR)
        os.makedirs(sg_vault_dir)
        with open(os.path.join(sg_vault_dir, 'some_file'), 'w') as f:
            f.write('internal')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__ignores_dotfiles(self):
        with open(os.path.join(self.tmp_dir, '.hidden'), 'w') as f:
            f.write('hidden')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert result == {}

    def test_scan__finds_regular_files(self):
        with open(os.path.join(self.tmp_dir, 'readme.md'), 'w') as f:
            f.write('hello')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'readme.md' in result
        assert result['readme.md']['size'] == 5

    def test_scan__nested_files(self):
        os.makedirs(os.path.join(self.tmp_dir, 'docs'))
        with open(os.path.join(self.tmp_dir, 'docs', 'api.md'), 'w') as f:
            f.write('api docs')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'docs/api.md' in result

    def test_scan__forward_slashes(self):
        os.makedirs(os.path.join(self.tmp_dir, 'a', 'b'))
        with open(os.path.join(self.tmp_dir, 'a', 'b', 'c.txt'), 'w') as f:
            f.write('deep')
        result = self.sync._scan_local_directory(self.tmp_dir)
        assert 'a/b/c.txt' in result


class Test_Vault__Sync__Init_And_Status:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=Vault__Crypto(), api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_init__creates_vault_structure(self):
        vault_dir = os.path.join(self.tmp_dir, 'my-vault')
        result    = self.sync.init(vault_dir)
        assert os.path.isdir(os.path.join(vault_dir, SG_VAULT_DIR))
        assert os.path.isfile(os.path.join(vault_dir, SG_VAULT_DIR, 'local', 'vault_key'))
        assert 'vault_key' in result
        assert 'vault_id' in result

    def test_init__with_custom_vault_key(self):
        vault_dir = os.path.join(self.tmp_dir, 'custom-vault')
        result    = self.sync.init(vault_dir, vault_key='my-custom-key:abcd1234')
        assert result['vault_key'] == 'my-custom-key:abcd1234'
        assert result['vault_id']  == 'abcd1234'

    def test_init__non_empty_directory_fails(self):
        vault_dir = os.path.join(self.tmp_dir, 'non-empty')
        os.makedirs(vault_dir)
        with open(os.path.join(vault_dir, 'existing.txt'), 'w') as f:
            f.write('already here')
        import pytest
        with pytest.raises(RuntimeError, match='not empty'):
            self.sync.init(vault_dir)

    def test_status__clean_after_init(self):
        vault_dir = os.path.join(self.tmp_dir, 'clean-vault')
        self.sync.init(vault_dir)
        status = self.sync.status(vault_dir)
        assert status['clean']   is True
        assert status['added']   == []
        assert status['modified'] == []
        assert status['deleted']  == []

    def test_status__detects_added_file(self):
        vault_dir = os.path.join(self.tmp_dir, 'add-vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'new-file.txt'), 'w') as f:
            f.write('new content')
        status = self.sync.status(vault_dir)
        assert 'new-file.txt' in status['added']
        assert status['clean'] is False

    def test_commit__commits_new_files(self):
        vault_dir = os.path.join(self.tmp_dir, 'commit-vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'test.txt'), 'w') as f:
            f.write('commit me')
        result = self.sync.commit(vault_dir)
        assert 'commit_id' in result
        assert 'branch_id' in result

    def test_commit__then_status_clean(self):
        vault_dir = os.path.join(self.tmp_dir, 'commit-clean-vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(vault_dir)
        status = self.sync.status(vault_dir)
        assert status['clean'] is True


class Test_Vault__Sync__Remove_Empty_Dirs:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sync    = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_removes_single_empty_dir(self):
        empty = os.path.join(self.tmp_dir, 'empty')
        os.makedirs(empty)
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert 'empty' in removed
        assert not os.path.isdir(empty)

    def test_removes_nested_empty_dirs(self):
        nested = os.path.join(self.tmp_dir, 'a', 'b', 'c')
        os.makedirs(nested)
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert not os.path.isdir(os.path.join(self.tmp_dir, 'a'))
        assert len(removed) == 3   # c, b, a all removed

    def test_keeps_dir_with_files(self):
        nonempty = os.path.join(self.tmp_dir, 'nonempty')
        os.makedirs(nonempty)
        with open(os.path.join(nonempty, 'file.txt'), 'w') as f:
            f.write('data')
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert removed == []
        assert os.path.isdir(nonempty)

    def test_skips_sg_vault_dir(self):
        sg = os.path.join(self.tmp_dir, '.sg_vault', 'bare')
        os.makedirs(sg)
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert removed == []
        assert os.path.isdir(sg)

    def test_skips_other_dotdirs(self):
        dotdir = os.path.join(self.tmp_dir, '.hidden', 'sub')
        os.makedirs(dotdir)
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert removed == []

    def test_mixed_keeps_nonempty_removes_empty(self):
        kept  = os.path.join(self.tmp_dir, 'kept')
        empty = os.path.join(self.tmp_dir, 'empty')
        os.makedirs(kept)
        os.makedirs(empty)
        with open(os.path.join(kept, 'x.txt'), 'w') as f:
            f.write('x')
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert 'empty' in removed
        assert os.path.isdir(kept)
        assert not os.path.isdir(empty)

    def test_no_empty_dirs_returns_empty_list(self):
        removed = self.sync._remove_empty_dirs(self.tmp_dir)
        assert removed == []
