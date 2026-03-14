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

    def test_is_v2_vault(self):
        assert self.storage.is_v2_vault(self.tmp_dir) is False
        self.storage.create_bare_structure(self.tmp_dir)
        assert self.storage.is_v2_vault(self.tmp_dir) is True

    def test_is_v1_vault(self):
        assert self.storage.is_v1_vault(self.tmp_dir) is False
        sg_dir = os.path.join(self.tmp_dir, '.sg_vault')
        refs_dir = os.path.join(sg_dir, 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'head'), 'w') as f:
            f.write('abc123')
        assert self.storage.is_v1_vault(self.tmp_dir) is True

    def test_path_helpers(self):
        self.storage.create_bare_structure(self.tmp_dir)
        assert self.storage.object_path(self.tmp_dir, 'obj-abc123').endswith('obj-abc123')
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
