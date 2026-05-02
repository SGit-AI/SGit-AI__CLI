"""Tests that Vault__Test_Env is importable from its new canonical location."""
from tests._helpers.vault_test_env import Vault__Test_Env


class Test_Helpers_Relocation:

    def test_vault_test_env_importable_from_helpers(self):
        assert Vault__Test_Env is not None

    def test_vault_test_env_has_setup_single_vault(self):
        assert hasattr(Vault__Test_Env, 'setup_single_vault')

    def test_vault_test_env_has_setup_two_clones(self):
        assert hasattr(Vault__Test_Env, 'setup_two_clones')

    def test_vault_test_env_has_restore(self):
        assert hasattr(Vault__Test_Env, 'restore')

    def test_forwarding_shim_also_works(self):
        from tests.unit.sync.vault_test_env import Vault__Test_Env as VTE_shim
        assert VTE_shim is Vault__Test_Env
