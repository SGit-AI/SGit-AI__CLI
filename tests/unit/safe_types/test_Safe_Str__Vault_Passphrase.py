import pytest
from sg_send_cli.safe_types.Safe_Str__Vault_Passphrase import Safe_Str__Vault_Passphrase


class Test_Safe_Str__Vault_Passphrase:

    def test_valid_passphrase(self):
        pp = Safe_Str__Vault_Passphrase('my secret passphrase')
        assert pp == 'my secret passphrase'

    def test_special_chars_allowed(self):
        pp = Safe_Str__Vault_Passphrase('P@ss!w0rd#$%^&*()')
        assert pp == 'P@ss!w0rd#$%^&*()'

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Passphrase('')

    def test_none_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Passphrase(None)

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Passphrase('a' * 257)

    def test_max_length_accepted(self):
        pp = Safe_Str__Vault_Passphrase('a' * 256)
        assert len(pp) == 256

    def test_type_preserved(self):
        pp = Safe_Str__Vault_Passphrase('test')
        assert type(pp).__name__ == 'Safe_Str__Vault_Passphrase'
