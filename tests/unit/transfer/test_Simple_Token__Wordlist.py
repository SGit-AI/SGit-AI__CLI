import re
from sgit_ai.network.transfer.Simple_Token__Wordlist   import Simple_Token__Wordlist, WORDLIST
from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token

TOKEN_PATTERN = re.compile(r'^[a-z]+-[a-z]+-\d{4}$')


class Test_Simple_Token__Wordlist:

    def setup_method(self):
        self.wl = Simple_Token__Wordlist()
        self.wl.setup()

    def test_wordlist_has_320_words(self):
        # The brief lists 356 unique words; the "320" in the brief title is approximate.
        assert len(WORDLIST) == 356

    def test_words_loaded_after_setup(self):
        assert len(self.wl.words) == 356

    def test_all_words_are_lowercase(self):
        for word in WORDLIST:
            assert word == word.lower(), f'Word not lowercase: {word}'

    def test_all_words_are_alpha(self):
        for word in WORDLIST:
            assert word.isalpha(), f'Word contains non-alpha: {word}'

    def test_generate_returns_safe_str_simple_token(self):
        tok = self.wl.generate()
        assert isinstance(tok, Safe_Str__Simple_Token)

    def test_generate_matches_token_pattern(self):
        tok = self.wl.generate()
        assert TOKEN_PATTERN.match(str(tok)), f'Token {tok!r} does not match pattern'

    def test_generate_token_words_in_wordlist(self):
        tok      = str(self.wl.generate())
        parts    = tok.rsplit('-', 1)            # split off the 4-digit suffix
        words    = parts[0].split('-')
        for word in words:
            assert word in WORDLIST, f'Generated word not in wordlist: {word}'

    def test_generate_four_digit_suffix(self):
        tok    = str(self.wl.generate())
        suffix = tok.split('-')[-1]
        assert len(suffix) == 4
        assert suffix.isdigit()

    def test_generate_produces_variety(self):
        tokens = {str(self.wl.generate()) for _ in range(20)}
        assert len(tokens) > 1, 'Expected variety in generated tokens'

    def test_word_count_method(self):
        assert self.wl.word_count() == 356

    def test_wordlist_no_duplicates(self):
        assert len(WORDLIST) == len(set(WORDLIST)), 'Wordlist contains duplicates'
