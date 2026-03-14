import pytest
from sg_send_cli.safe_types.Safe_Str__Branch_Id import Safe_Str__Branch_Id


class Test_Safe_Str__Branch_Id:

    def test_valid_named_branch(self):
        bid = Safe_Str__Branch_Id('branch-named-a1b2c3d4')
        assert bid == 'branch-named-a1b2c3d4'

    def test_valid_clone_branch(self):
        bid = Safe_Str__Branch_Id('branch-clone-deadbeef')
        assert bid == 'branch-clone-deadbeef'

    def test_valid_long_id(self):
        bid = Safe_Str__Branch_Id('branch-named-' + 'a' * 64)
        assert str(bid).startswith('branch-named-')

    def test_empty_allowed(self):
        bid = Safe_Str__Branch_Id('')
        assert bid == ''

    def test_uppercase_converted_to_lower(self):
        bid = Safe_Str__Branch_Id('branch-named-A1B2C3D4')
        assert bid == 'branch-named-a1b2c3d4'

    def test_invalid_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Branch_Id('branch-other-a1b2c3d4')

    def test_missing_id_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Branch_Id('branch-named-')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Branch_Id('branch-named-xyz123zz')

    def test_type_preserved(self):
        bid = Safe_Str__Branch_Id('branch-clone-a1b2c3d4')
        assert type(bid).__name__ == 'Safe_Str__Branch_Id'
