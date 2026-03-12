import pytest
from sg_send_cli.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token, ACCESS_TOKEN__MAX_LENGTH


class Test_Safe_Str__Access_Token__Boundary:

    def test_max_length_value(self):
        assert ACCESS_TOKEN__MAX_LENGTH == 2048

    def test_at_max_length_accepted(self):
        token = Safe_Str__Access_Token('a' * 2048)
        assert len(token) == 2048

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Access_Token('a' * 2049)

    def test_whitespace_sanitized(self):
        token = Safe_Str__Access_Token('  my-token  ')
        assert ' ' not in str(token)

    def test_dots_allowed(self):
        token = Safe_Str__Access_Token('eyJhbG.payload.signature')
        assert '.' in str(token)

    def test_dashes_allowed(self):
        token = Safe_Str__Access_Token('my-long-token-value')
        assert '-' in str(token)

    def test_underscores_allowed(self):
        token = Safe_Str__Access_Token('my_token_value')
        assert '_' in str(token)

    def test_at_sign_sanitized(self):
        token = Safe_Str__Access_Token('tok@en')
        assert '@' not in str(token)

    def test_semicolon_sanitized(self):
        token = Safe_Str__Access_Token('tok;en')
        assert ';' not in str(token)

    def test_angle_brackets_sanitized(self):
        token = Safe_Str__Access_Token('tok<script>en')
        assert '<' not in str(token)
        assert '>' not in str(token)

    def test_spaces_sanitized(self):
        token = Safe_Str__Access_Token('tok en')
        assert ' ' not in str(token)

    def test_newline_sanitized(self):
        token = Safe_Str__Access_Token('tok\nen')
        assert '\n' not in str(token)

    def test_type_preserved_after_assignment(self):
        token = Safe_Str__Access_Token('test-token')
        assert type(token).__name__ == 'Safe_Str__Access_Token'

    def test_none_gives_empty(self):
        token = Safe_Str__Access_Token(None)
        assert token == ''
