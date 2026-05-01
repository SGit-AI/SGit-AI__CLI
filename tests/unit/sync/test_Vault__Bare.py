import json
import os
import tempfile
import shutil
import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sgit_ai.sync.Vault__Bare        import Vault__Bare
from sgit_ai.sync.Vault__Sync        import Vault__Sync


class Test_Vault__Bare:

    @pytest.fixture(autouse=True)
    def _setup(self, bare_vault_workspace):
        ws            = bare_vault_workspace('small_vault')
        self.tmp_dir  = ws['tmp_dir']
        self.crypto   = ws['crypto']
        self.bare     = ws['bare']
        self.sync     = ws['sync']
        self.vault_key = ws['vault_key']

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

    @pytest.fixture(autouse=True)
    def _setup(self, bare_vault_workspace):
        ws            = bare_vault_workspace('read_list_vault')
        self.tmp_dir  = ws['tmp_dir']
        self.crypto   = ws['crypto']
        self.bare     = ws['bare']
        self.sync     = ws['sync']
        self.vault_key = ws['vault_key']

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
