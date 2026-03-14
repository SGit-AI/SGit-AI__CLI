import pytest
from sg_send_cli.safe_types.Safe_Str__Content_Hash import Safe_Str__Content_Hash


class Test_Safe_Str__Content_Hash:

    def test_valid_hash(self):
        ch = Safe_Str__Content_Hash('a1b2c3d4e5f6')
        assert ch == 'a1b2c3d4e5f6'

    def test_empty_allowed(self):
        ch = Safe_Str__Content_Hash('')
        assert ch == ''

    def test_uppercase_lowered(self):
        ch = Safe_Str__Content_Hash('A1B2C3D4E5F6')
        assert ch == 'a1b2c3d4e5f6'

    def test_too_short_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Content_Hash('a1b2c3')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Content_Hash('a1b2c3d4e5gz')

    def test_type_preserved(self):
        ch = Safe_Str__Content_Hash('a1b2c3d4e5f6')
        assert type(ch).__name__ == 'Safe_Str__Content_Hash'
