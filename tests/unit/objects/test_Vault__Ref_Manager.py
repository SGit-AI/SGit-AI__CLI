import os
import tempfile
from sg_send_cli.objects.Vault__Ref_Manager import Vault__Ref_Manager


class Test_Vault__Ref_Manager:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.vault_path = self.tmp_dir
        self.ref_mgr    = Vault__Ref_Manager(vault_path=self.vault_path)

    def test_is_initialized_false_initially(self):
        assert self.ref_mgr.is_initialized() is False

    def test_read_head_returns_none_when_not_initialized(self):
        assert self.ref_mgr.read_head() is None

    def test_write_and_read_head(self):
        self.ref_mgr.write_head('a1b2c3d4e5f6')
        assert self.ref_mgr.read_head() == 'a1b2c3d4e5f6'

    def test_is_initialized_after_write(self):
        self.ref_mgr.write_head('a1b2c3d4e5f6')
        assert self.ref_mgr.is_initialized() is True

    def test_write_creates_refs_directory(self):
        self.ref_mgr.write_head('a1b2c3d4e5f6')
        refs_dir = os.path.join(self.vault_path, 'refs')
        assert os.path.isdir(refs_dir)

    def test_overwrite_head(self):
        self.ref_mgr.write_head('a1b2c3d4e5f6')
        self.ref_mgr.write_head('b2c3d4e5f6a1')
        assert self.ref_mgr.read_head() == 'b2c3d4e5f6a1'

    def test_head_file_path(self):
        path = self.ref_mgr._head_path()
        assert path.endswith(os.path.join('refs', 'head'))

    def test_read_head_empty_file_returns_none(self):
        refs_dir = os.path.join(self.vault_path, 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'head'), 'w') as f:
            f.write('')
        assert self.ref_mgr.read_head() is None
