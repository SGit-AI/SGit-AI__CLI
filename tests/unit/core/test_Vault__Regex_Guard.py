import re

import pytest

from sgit_ai.core.Vault__Errors      import Vault__Revision_Error
from sgit_ai.core.Vault__Regex_Guard import Vault__Regex_Guard, MAX_PATTERN_CHARS


class Test_Vault__Regex_Guard:

    def setup_method(self):
        self.guard = Vault__Regex_Guard()

    def test_a_good_pattern_compiles_with_the_flags_asked_for(self):
        assert self.guard.check('fix(es)?', 'grep').search('FIXES')
        assert self.guard.check('Fix', 'grep', flags=0).search('fix') is None

    @pytest.mark.parametrize('pattern', ['(a+)+$', '(a+|b)+$', '((a+))+$', '(a{2,})*', '(a+){10}'])
    def test_nested_repetitions_are_refused_by_name(self, pattern):
        with pytest.raises(Vault__Revision_Error, match="grep .* repeats a repetition"):
            self.guard.check(pattern, 'grep')

    @pytest.mark.parametrize('pattern', ['(ab*){2}', '[a-z]+(-[a-z]+)*', '(/[^/]+)+', 'plain text'])
    def test_safe_shapes_pass(self, pattern):
        assert self.guard.check(pattern)

    def test_invalid_and_too_long(self):
        with pytest.raises(Vault__Revision_Error, match='not a valid regular expression'):
            self.guard.check('(', '-G')
        with pytest.raises(Vault__Revision_Error, match=f'the limit is {MAX_PATTERN_CHARS}'):
            self.guard.check('a' * (MAX_PATTERN_CHARS + 1), '-G')
