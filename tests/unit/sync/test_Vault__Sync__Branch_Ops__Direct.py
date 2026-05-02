"""Direct instantiation tests for Vault__Sync__Branch_Ops (Tightening 5)."""
import pytest

from sgit_ai.sync.Vault__Sync__Branch_Ops import Vault__Sync__Branch_Ops
from tests.unit.sync.vault_test_env        import Vault__Test_Env


class Test_Vault__Sync__Branch_Ops__Direct:
    """Instantiate Vault__Sync__Branch_Ops directly, not via the Vault__Sync facade."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env  = self._env.restore()
        self.ops  = Vault__Sync__Branch_Ops(crypto=self.env.crypto, api=self.env.api)

    def teardown_method(self):
        self.env.cleanup()

    def test_direct_instantiation(self):
        assert isinstance(self.ops, Vault__Sync__Branch_Ops)

    def test_branches_returns_dict_with_list(self):
        result = self.ops.branches(self.env.vault_dir)
        assert 'branches' in result
        assert isinstance(result['branches'], list)

    def test_branches_has_at_least_two_entries(self):
        result   = self.ops.branches(self.env.vault_dir)
        branches = result['branches']
        assert len(branches) >= 2

    def test_branches_has_current_flag(self):
        result      = self.ops.branches(self.env.vault_dir)
        has_current = any(b['is_current'] for b in result['branches'])
        assert has_current

    def test_branches_includes_my_branch_id(self):
        result = self.ops.branches(self.env.vault_dir)
        assert result['my_branch_id'].startswith('branch-clone-')

    def test_remote_list_empty_on_fresh_vault(self):
        result = self.ops.remote_list(self.env.vault_dir)
        assert 'remotes' in result
        assert isinstance(result['remotes'], list)

    def test_remote_add_and_list(self):
        directory = self.env.vault_dir
        self.ops.remote_add(directory, 'origin', 'https://example.com', 'vault123')
        remotes = self.ops.remote_list(directory)
        assert any(r['name'] == 'origin' for r in remotes['remotes'])

    def test_remote_add_returns_name_and_url(self):
        result = self.ops.remote_add(self.env.vault_dir, 'upstream', 'https://up.example.com', 'vabc')
        assert result['name'] == 'upstream'
        assert result['url']  == 'https://up.example.com'

    def test_remote_remove_existing(self):
        directory = self.env.vault_dir
        self.ops.remote_add(directory, 'to-remove', 'https://r.example.com', 'vxyz')
        result = self.ops.remote_remove(directory, 'to-remove')
        assert result['removed'] == 'to-remove'

    def test_remote_remove_missing_raises(self):
        with pytest.raises(RuntimeError, match='Remote not found'):
            self.ops.remote_remove(self.env.vault_dir, 'nonexistent')
