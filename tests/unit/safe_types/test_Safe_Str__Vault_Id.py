import pytest
from sg_send_cli.safe_types.Safe_Str__Vault_Id import Safe_Str__Vault_Id


class Test_Safe_Str__Vault_Id:

    def test_valid_vault_id(self):
        vid = Safe_Str__Vault_Id('abcd1234')
        assert vid == 'abcd1234'

    def test_lowercase_conversion(self):
        vid = Safe_Str__Vault_Id('ABCD1234')
        assert vid == 'abcd1234'

    def test_whitespace_trimmed(self):
        vid = Safe_Str__Vault_Id('  abcd1234  ')
        assert vid == 'abcd1234'

    def test_empty_allowed(self):
        vid = Safe_Str__Vault_Id('')
        assert vid == ''

    def test_none_gives_empty(self):
        vid = Safe_Str__Vault_Id(None)
        assert vid == ''

    # def test_wrong_length_rejected(self):
    #     with pytest.raises(ValueError):
    #         Safe_Str__Vault_Id('abcd')
    #
    # def test_too_long_rejected(self):
    #     with pytest.raises(ValueError):
    #         Safe_Str__Vault_Id('abcd12345')
    #
    # def test_non_alphanumeric_rejected(self):
    #     with pytest.raises(ValueError):
    #         Safe_Str__Vault_Id('abcd-123')
    #
    # def test_uppercase_only_rejected(self):
    #     with pytest.raises(ValueError):
    #         Safe_Str__Vault_Id('ABCD-XYZ')

    def test_alphanumeric_vault_id_accepted(self):
        vid = Safe_Str__Vault_Id('12cpxeq9')
        assert vid == '12cpxeq9'

    def test_type_preserved(self):
        vid = Safe_Str__Vault_Id('abcd1234')
        assert type(vid).__name__ == 'Safe_Str__Vault_Id'
