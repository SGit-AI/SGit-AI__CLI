import pytest
from sgit_ai.safe_types.Safe_Str__Diff_Mode import Safe_Str__Diff_Mode


class Test_Safe_Str__Diff_Mode:

    def test_valid_head(self):
        mode = Safe_Str__Diff_Mode('head')
        assert mode == 'head'

    def test_valid_remote(self):
        mode = Safe_Str__Diff_Mode('remote')
        assert mode == 'remote'

    def test_valid_commit(self):
        mode = Safe_Str__Diff_Mode('commit')
        assert mode == 'commit'

    def test_empty_allowed(self):
        mode = Safe_Str__Diff_Mode('')
        assert mode == ''

    def test_none_gives_empty(self):
        mode = Safe_Str__Diff_Mode(None)
        assert mode == ''

    def test_whitespace_trimmed(self):
        mode = Safe_Str__Diff_Mode('  head  ')
        assert mode == 'head'

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Diff_Mode('staging')

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Diff_Mode('HEAD')

    def test_partial_match_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Diff_Mode('hea')

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Diff_Mode('local')

    def test_type_preserved(self):
        mode = Safe_Str__Diff_Mode('head')
        assert type(mode).__name__ == 'Safe_Str__Diff_Mode'

    def test_max_length(self):
        assert Safe_Str__Diff_Mode.max_length == 16

    def test_max_length_respected(self):
        mode = Safe_Str__Diff_Mode('commit')
        assert len(mode) <= 16

    def test_all_three_modes_are_distinct(self):
        modes = {Safe_Str__Diff_Mode('head'),
                 Safe_Str__Diff_Mode('remote'),
                 Safe_Str__Diff_Mode('commit')}
        assert len(modes) == 3
