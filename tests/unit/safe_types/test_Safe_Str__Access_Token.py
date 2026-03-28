import pytest
from sgit_ai.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token


class Test_Safe_Str__Access_Token:

    def test_valid_token(self):
        token = Safe_Str__Access_Token('eyJhbGciOiJIUzI1NiJ9.payload.signature')
        assert token == 'eyJhbGciOiJIUzI1NiJ9.payload.signature'

    def test_empty_allowed(self):
        token = Safe_Str__Access_Token('')
        assert token == ''

    def test_special_chars_sanitized(self):
        token = Safe_Str__Access_Token('tok@en!')
        assert '@' not in token
        assert '!' not in token

    def test_type_preserved(self):
        token = Safe_Str__Access_Token('test-token')
        assert type(token).__name__ == 'Safe_Str__Access_Token'
