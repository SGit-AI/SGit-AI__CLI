import pytest
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token


class Test_Safe_Str__Simple_Token:

    def test_valid_token(self):
        tok = Safe_Str__Simple_Token('maple-river-7291')
        assert tok == 'maple-river-7291'

    def test_valid_token_lowercase_words(self):
        tok = Safe_Str__Simple_Token('test-token-1234')
        assert tok == 'test-token-1234'

    def test_whitespace_trimmed(self):
        tok = Safe_Str__Simple_Token('  able-acid-0001  ')
        assert tok == 'able-acid-0001'

    def test_empty_allowed(self):
        tok = Safe_Str__Simple_Token('')
        assert tok == ''

    def test_none_gives_empty(self):
        tok = Safe_Str__Simple_Token(None)
        assert tok == ''

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Simple_Token('word-only')

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Simple_Token('MAPLE-RIVER-7291')

    def test_wrong_digit_count_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Simple_Token('maple-river-72')

    def test_five_digit_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Simple_Token('maple-river-72910')

    def test_type_preserved(self):
        tok = Safe_Str__Simple_Token('able-acid-0001')
        assert type(tok).__name__ == 'Safe_Str__Simple_Token'

    def test_four_part_token_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Simple_Token('maple-river-extra-1234')
