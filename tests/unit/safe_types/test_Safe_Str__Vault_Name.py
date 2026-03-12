import pytest
from sg_send_cli.safe_types.Safe_Str__Vault_Name import Safe_Str__Vault_Name, VAULT_NAME__MAX_LENGTH


class Test_Safe_Str__Vault_Name:

    def test_valid_name(self):
        name = Safe_Str__Vault_Name('My Vault')
        assert name == 'My Vault'

    def test_valid_with_dashes(self):
        name = Safe_Str__Vault_Name('my-vault-name')
        assert name == 'my-vault-name'

    def test_valid_with_underscores(self):
        name = Safe_Str__Vault_Name('my_vault_name')
        assert name == 'my_vault_name'

    def test_valid_with_dots(self):
        name = Safe_Str__Vault_Name('vault.v1')
        assert name == 'vault.v1'

    def test_valid_with_numbers(self):
        name = Safe_Str__Vault_Name('vault123')
        assert name == 'vault123'

    def test_empty_allowed(self):
        name = Safe_Str__Vault_Name('')
        assert name == ''

    def test_none_gives_empty(self):
        name = Safe_Str__Vault_Name(None)
        assert name == ''

    def test_max_length(self):
        assert VAULT_NAME__MAX_LENGTH == 128

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Name('a' * 129)

    def test_at_max_length_accepted(self):
        name = Safe_Str__Vault_Name('a' * 128)
        assert len(name) == 128

    def test_special_chars_sanitized(self):
        name = Safe_Str__Vault_Name('vault@name!')
        assert '@' not in str(name)
        assert '!' not in str(name)

    def test_slashes_sanitized(self):
        name = Safe_Str__Vault_Name('vault/name')
        assert '/' not in str(name)

    def test_spaces_allowed(self):
        name = Safe_Str__Vault_Name('My Vault Name')
        assert ' ' in str(name)

    def test_type_preserved(self):
        name = Safe_Str__Vault_Name('test')
        assert type(name).__name__ == 'Safe_Str__Vault_Name'
