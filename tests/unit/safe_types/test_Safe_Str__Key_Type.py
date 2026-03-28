import pytest
from sgit_ai.safe_types.Safe_Str__Key_Type import Safe_Str__Key_Type


class Test_Safe_Str__Key_Type:

    def test_valid_vault_key(self):
        t = Safe_Str__Key_Type('vault_key')
        assert t == 'vault_key'

    def test_valid_none(self):
        t = Safe_Str__Key_Type('none')
        assert t == 'none'

    def test_valid_pki(self):
        t = Safe_Str__Key_Type('pki')
        assert t == 'pki'

    def test_valid_password(self):
        t = Safe_Str__Key_Type('password')
        assert t == 'password'

    def test_empty_allowed(self):
        t = Safe_Str__Key_Type('')
        assert t == ''

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Type('unknown')

    def test_type_preserved(self):
        t = Safe_Str__Key_Type('vault_key')
        assert type(t).__name__ == 'Safe_Str__Key_Type'
