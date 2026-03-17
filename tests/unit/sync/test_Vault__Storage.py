import os
import tempfile
import shutil
from sg_send_cli.sync.Vault__Storage import Vault__Storage


class Test_Vault__Storage:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_bare_structure(self):
        self.storage.create_bare_structure(self.tmp_dir)
        assert os.path.isdir(self.storage.bare_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_data_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_refs_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_keys_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_indexes_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_pending_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.bare_branches_dir(self.tmp_dir))
        assert os.path.isdir(self.storage.local_dir(self.tmp_dir))

    def test_is_vault(self):
        assert self.storage.is_vault(self.tmp_dir) is False
        self.storage.create_bare_structure(self.tmp_dir)
        assert self.storage.is_vault(self.tmp_dir) is True

    def test_path_helpers(self):
        self.storage.create_bare_structure(self.tmp_dir)
        assert self.storage.object_path(self.tmp_dir, 'obj-cas-imm-abc123def456').endswith('obj-cas-imm-abc123def456')
        assert self.storage.ref_path(self.tmp_dir, 'ref-abc123').endswith('ref-abc123')
        assert self.storage.key_path(self.tmp_dir, 'key-abc123').endswith('key-abc123')
        assert self.storage.index_path(self.tmp_dir, 'idx-abc123').endswith('idx-abc123')

    def test_vault_key_path(self):
        path = self.storage.vault_key_path(self.tmp_dir)
        assert path.endswith('local/vault_key')

    def test_local_config_path(self):
        path = self.storage.local_config_path(self.tmp_dir)
        assert 'local' in path
        assert path.endswith('config.json')
