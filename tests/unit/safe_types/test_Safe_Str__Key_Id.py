import pytest
from sg_send_cli.safe_types.Safe_Str__Key_Id import Safe_Str__Key_Id


class Test_Safe_Str__Key_Id:

    def test_valid_key(self):
        kid = Safe_Str__Key_Id('key-rnd-imm-a1b2c3d4')
        assert kid == 'key-rnd-imm-a1b2c3d4'

    def test_valid_long_key(self):
        kid = Safe_Str__Key_Id('key-rnd-imm-' + 'ab' * 16)
        assert str(kid).startswith('key-rnd-imm-')

    def test_empty_allowed(self):
        kid = Safe_Str__Key_Id('')
        assert kid == ''

    def test_uppercase_lowered(self):
        kid = Safe_Str__Key_Id('key-rnd-imm-AABB1122')
        assert kid == 'key-rnd-imm-aabb1122'

    def test_missing_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Id('a1b2c3d4')

    def test_old_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Id('key-a1b2c3d4')

    def test_type_preserved(self):
        kid = Safe_Str__Key_Id('key-rnd-imm-deadbeef')
        assert type(kid).__name__ == 'Safe_Str__Key_Id'
