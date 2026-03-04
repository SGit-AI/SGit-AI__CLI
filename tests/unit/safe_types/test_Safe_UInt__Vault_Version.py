import pytest
from sg_send_cli.safe_types.Safe_UInt__Vault_Version import Safe_UInt__Vault_Version


class Test_Safe_UInt__Vault_Version:

    def test_valid_version(self):
        v = Safe_UInt__Vault_Version(1)
        assert v == 1

    def test_zero_allowed(self):
        v = Safe_UInt__Vault_Version(0)
        assert v == 0

    def test_max_allowed(self):
        v = Safe_UInt__Vault_Version(999999)
        assert v == 999999

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Vault_Version(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError):
            Safe_UInt__Vault_Version(1000000)

    def test_type_preserved(self):
        v = Safe_UInt__Vault_Version(42)
        assert type(v).__name__ == 'Safe_UInt__Vault_Version'
