import pytest
from sg_send_cli.safe_types.Safe_Str__Key_Id import Safe_Str__Key_Id


class Test_Safe_Str__Key_Id:

    def test_valid_key(self):
        kid = Safe_Str__Key_Id('key-a1b2c3d4')
        assert kid == 'key-a1b2c3d4'

    def test_empty_allowed(self):
        kid = Safe_Str__Key_Id('')
        assert kid == ''

    def test_uppercase_lowered(self):
        kid = Safe_Str__Key_Id('key-AABB1122')
        assert kid == 'key-aabb1122'

    def test_missing_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Id('a1b2c3d4')

    def test_type_preserved(self):
        kid = Safe_Str__Key_Id('key-deadbeef')
        assert type(kid).__name__ == 'Safe_Str__Key_Id'
