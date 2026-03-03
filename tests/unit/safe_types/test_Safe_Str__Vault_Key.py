import pytest
from sg_send_cli.safe_types.Safe_Str__Vault_Key import Safe_Str__Vault_Key


class Test_Safe_Str__Vault_Key:

    def test_valid_vault_key(self):
        key = Safe_Str__Vault_Key('my passphrase:abcd1234:abc123def456')
        assert key == 'my passphrase:abcd1234:abc123def456'

    def test_empty_allowed(self):
        key = Safe_Str__Vault_Key('')
        assert key == ''

    def test_missing_parts_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Key('just-a-passphrase')

    def test_invalid_vault_id_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Key('pass:ZZZZ1234:abc123def456')

    def test_invalid_transfer_id_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Vault_Key('pass:abcd1234:short')

    def test_type_preserved(self):
        key = Safe_Str__Vault_Key('pass:abcd1234:abc123def456')
        assert type(key).__name__ == 'Safe_Str__Vault_Key'
