import os
import tempfile
import pytest
from sg_send_cli.sync.Vault__Legacy_Guard import Vault__Legacy_Guard, Legacy_Vault_Error


class Test_Vault__Legacy_Guard:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.guard   = Vault__Legacy_Guard()

    def _create_sg_vault(self):
        sg_vault = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(sg_vault, exist_ok=True)
        return sg_vault

    def test_fresh_directory_passes(self):
        self.guard.check_vault_format(self.tmp_dir)

    def test_empty_sg_vault_passes(self):
        self._create_sg_vault()
        self.guard.check_vault_format(self.tmp_dir)

    def test_legacy_vault_detected(self):
        sg_vault = self._create_sg_vault()
        with open(os.path.join(sg_vault, 'tree.json'), 'w') as f:
            f.write('{}')
        with pytest.raises(Legacy_Vault_Error) as exc_info:
            self.guard.check_vault_format(self.tmp_dir)
        assert 'legacy format' in str(exc_info.value)
        assert 'vault.sgraph.ai' in str(exc_info.value)

    def test_new_format_vault_passes(self):
        sg_vault = self._create_sg_vault()
        with open(os.path.join(sg_vault, 'tree.json'), 'w') as f:
            f.write('{}')
        refs_dir = os.path.join(sg_vault, 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'head'), 'w') as f:
            f.write('a1b2c3d4e5f6')
        self.guard.check_vault_format(self.tmp_dir)

    def test_refs_head_without_tree_passes(self):
        sg_vault = self._create_sg_vault()
        refs_dir = os.path.join(sg_vault, 'refs')
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, 'head'), 'w') as f:
            f.write('a1b2c3d4e5f6')
        self.guard.check_vault_format(self.tmp_dir)

    def test_error_message_is_helpful(self):
        sg_vault = self._create_sg_vault()
        with open(os.path.join(sg_vault, 'tree.json'), 'w') as f:
            f.write('{}')
        with pytest.raises(Legacy_Vault_Error) as exc_info:
            self.guard.check_vault_format(self.tmp_dir)
        msg = str(exc_info.value)
        assert 'web interface' in msg
        assert 'object store' in msg
