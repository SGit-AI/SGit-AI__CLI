import pytest
from sgit_ai.safe_types.Safe_Str__Base64_Data import Safe_Str__Base64_Data


class Test_Safe_Str__Base64_Data:

    def test_valid_base64(self):
        data = Safe_Str__Base64_Data('dGVzdA==')
        assert data == 'dGVzdA=='

    def test_empty_allowed(self):
        data = Safe_Str__Base64_Data('')
        assert data == ''

    def test_valid_with_plus_and_slash(self):
        data = Safe_Str__Base64_Data('abc+def/ghi=')
        assert data == 'abc+def/ghi='

    def test_alphanumeric_only(self):
        data = Safe_Str__Base64_Data('ABCDEFghij0123456789')
        assert data == 'ABCDEFghij0123456789'

    def test_invalid_chars_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Base64_Data('data with spaces')

    def test_special_chars_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Base64_Data('data!@#$')

    def test_type_preserved(self):
        data = Safe_Str__Base64_Data('dGVzdA==')
        assert type(data).__name__ == 'Safe_Str__Base64_Data'
