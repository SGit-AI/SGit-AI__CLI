import pytest
from sgit_ai.safe_types.Safe_Str__Diff_Mode import Safe_Str__Diff_Mode


class Test_Safe_Str__Diff_Mode:

    def test_valid_modes(self):
        assert str(Safe_Str__Diff_Mode('head'))   == 'head'
        assert str(Safe_Str__Diff_Mode('remote')) == 'remote'
        assert str(Safe_Str__Diff_Mode('commit')) == 'commit'

    def test_allow_empty(self):
        # allow_empty = True so empty string should be fine
        mode = Safe_Str__Diff_Mode('')
        assert str(mode) == ''

    def test_invalid_mode_raises(self):
        with pytest.raises((ValueError, Exception)):
            Safe_Str__Diff_Mode('invalid-mode')

    def test_max_length(self):
        assert Safe_Str__Diff_Mode.max_length == 16

    def test_trim_whitespace(self):
        # trim_whitespace = True
        mode = Safe_Str__Diff_Mode('  head  ')
        assert str(mode) == 'head'
