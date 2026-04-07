import json
import os
import tempfile
import shutil
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Bare        import Vault__Bare
from sgit_ai.sync.Vault__Sync        import Vault__Sync


class Test_Vault__Bare:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.bare      = Vault__Bare(crypto=self.crypto)
        self.sync      = Vault__Sync(crypto=self.crypto)
        self._create_test_vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_test_vault(self):
        """Create a vault using Vault__Sync, commit files, then make it bare."""
        result = self.sync.init(self.tmp_dir)
        self.vault_key = result['vault_key']

        # Add files
        with open(os.path.join(self.tmp_dir, 'config.json'), 'wb') as f:
            f.write(b'{"key": "value"}')
        os.makedirs(os.path.join(self.tmp_dir, 'deploy'), exist_ok=True)
        with open(os.path.join(self.tmp_dir, 'deploy', 'run.sh'), 'wb') as f:
            f.write(b'deploy script contents')

        commit_result = self.sync.commit(self.tmp_dir, 'add test files')

        # Advance named ref to match clone (simulates push)
        keys     = self.crypto.derive_keys_from_vault_key(self.vault_key)
        sg_dir   = os.path.join(self.tmp_dir, '.sg_vault')
        ref_mgr  = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        ref_mgr.write_ref(keys['ref_file_id'], commit_result['commit_id'], keys['read_key_bytes'])

        # Remove working copy files and vault key to simulate bare state
        os.remove(os.path.join(self.tmp_dir, 'config.json'))
        shutil.rmtree(os.path.join(self.tmp_dir, 'deploy'))
        vault_key_path = os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key')
        if os.path.isfile(vault_key_path):
            os.remove(vault_key_path)

    def test_is_bare__bare_vault(self):
        assert self.bare.is_bare(self.tmp_dir) is True

    def test_is_bare__with_vault_key(self):
        local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'vault_key'), 'w') as f:
            f.write(self.vault_key)
        assert self.bare.is_bare(self.tmp_dir) is False

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

    def test_clean__preserves_bare_structure(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        self.bare.clean(self.tmp_dir)
        assert os.path.isdir(os.path.join(self.tmp_dir, '.sg_vault', 'bare', 'data'))
        assert os.path.isdir(os.path.join(self.tmp_dir, '.sg_vault', 'bare', 'refs'))

    def test_roundtrip__checkout_clean_verify(self):
        self.bare.checkout(self.tmp_dir, self.vault_key)
        assert not self.bare.is_bare(self.tmp_dir)
        self.bare.clean(self.tmp_dir)
        assert self.bare.is_bare(self.tmp_dir)


class Test_Vault__Bare__Read_List:
    """Tests for read_file(), list_files(), and edge cases."""

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.bare     = Vault__Bare(crypto=self.crypto)
        self.sync     = Vault__Sync(crypto=self.crypto)
        self._create_bare_vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_bare_vault(self):
        """Init, commit files, advance named ref, then strip to bare state."""
        result         = self.sync.init(self.tmp_dir)
        self.vault_key = result['vault_key']

        with open(os.path.join(self.tmp_dir, 'readme.txt'), 'wb') as f:
            f.write(b'hello world')
        os.makedirs(os.path.join(self.tmp_dir, 'docs'), exist_ok=True)
        with open(os.path.join(self.tmp_dir, 'docs', 'guide.md'), 'wb') as f:
            f.write(b'# Guide')

        commit_result = self.sync.commit(self.tmp_dir, 'initial commit')

        keys   = self.crypto.derive_keys_from_vault_key(self.vault_key)
        sg_dir = os.path.join(self.tmp_dir, '.sg_vault')
        ref_mgr = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        ref_mgr.write_ref(keys['ref_file_id'], commit_result['commit_id'],
                          keys['read_key_bytes'])

        # Strip to bare state
        os.remove(os.path.join(self.tmp_dir, 'readme.txt'))
        shutil.rmtree(os.path.join(self.tmp_dir, 'docs'))
        vault_key_path = os.path.join(self.tmp_dir, '.sg_vault', 'local', 'vault_key')
        if os.path.isfile(vault_key_path):
            os.remove(vault_key_path)

    # --- list_files ---

    def test_list_files_returns_list(self):
        files = self.bare.list_files(self.tmp_dir, self.vault_key)
        assert isinstance(files, list)

    def test_list_files_count(self):
        files = self.bare.list_files(self.tmp_dir, self.vault_key)
        assert len(files) == 2

    def test_list_files_has_readme(self):
        paths = [f['path'] for f in self.bare.list_files(self.tmp_dir, self.vault_key)]
        assert 'readme.txt' in paths

    def test_list_files_has_nested_file(self):
        paths = [f['path'] for f in self.bare.list_files(self.tmp_dir, self.vault_key)]
        assert 'docs/guide.md' in paths

    def test_list_files_has_size(self):
        files = self.bare.list_files(self.tmp_dir, self.vault_key)
        readme = next(f for f in files if f['path'] == 'readme.txt')
        assert readme['size'] == len(b'hello world')

    def test_list_files_has_blob_id(self):
        files = self.bare.list_files(self.tmp_dir, self.vault_key)
        assert all('blob_id' in f for f in files)

    # --- read_file ---

    def test_read_file_returns_content(self):
        content = self.bare.read_file(self.tmp_dir, self.vault_key, 'readme.txt')
        assert content == b'hello world'

    def test_read_file_nested_path(self):
        content = self.bare.read_file(self.tmp_dir, self.vault_key, 'docs/guide.md')
        assert content == b'# Guide'

    def test_read_file_not_found_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='not found'):
            self.bare.read_file(self.tmp_dir, self.vault_key, 'nonexistent.txt')

    # --- dotfile filtering in _list_working_copy_files (line 112) ---

    def test_list_working_copy_excludes_dotfiles(self):
        """_list_working_copy_files skips files starting with '.'."""
        # Add a dotfile to the working directory
        with open(os.path.join(self.tmp_dir, '.hidden'), 'w') as f:
            f.write('secret')
        result = self.bare._list_working_copy_files(self.tmp_dir,
                    os.path.join(self.tmp_dir, '.sg_vault'))
        assert '.hidden' not in result
        assert not any(p.startswith('.') for p in result)
