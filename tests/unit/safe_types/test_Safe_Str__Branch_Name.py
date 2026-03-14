import pytest
from sg_send_cli.safe_types.Safe_Str__Branch_Name import Safe_Str__Branch_Name


class Test_Safe_Str__Branch_Name:

    def test_valid_current(self):
        bn = Safe_Str__Branch_Name('current')
        assert bn == 'current'

    def test_valid_with_underscores(self):
        bn = Safe_Str__Branch_Name('fp_br1_3c8f')
        assert bn == 'fp_br1_3c8f'

    def test_valid_with_hyphens(self):
        bn = Safe_Str__Branch_Name('my-branch')
        assert bn == 'my-branch'

    def test_empty_allowed(self):
        bn = Safe_Str__Branch_Name('')
        assert bn == ''

    def test_spaces_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Branch_Name('my branch')

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Branch_Name('a' * 65)

    def test_type_preserved(self):
        bn = Safe_Str__Branch_Name('current')
        assert type(bn).__name__ == 'Safe_Str__Branch_Name'
