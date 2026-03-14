import pytest
from sg_send_cli.safe_types.Safe_Str__Ref_Id import Safe_Str__Ref_Id


class Test_Safe_Str__Ref_Id:

    def test_valid_ref(self):
        rid = Safe_Str__Ref_Id('ref-a1b2c3d4')
        assert rid == 'ref-a1b2c3d4'

    def test_valid_long_ref(self):
        rid = Safe_Str__Ref_Id('ref-' + 'f' * 64)
        assert str(rid).startswith('ref-')

    def test_empty_allowed(self):
        rid = Safe_Str__Ref_Id('')
        assert rid == ''

    def test_uppercase_lowered(self):
        rid = Safe_Str__Ref_Id('ref-AABB1122')
        assert rid == 'ref-aabb1122'

    def test_missing_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Ref_Id('a1b2c3d4e5f6')

    def test_too_short_id_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Ref_Id('ref-a1b2c3')

    def test_type_preserved(self):
        rid = Safe_Str__Ref_Id('ref-a1b2c3d4')
        assert type(rid).__name__ == 'Safe_Str__Ref_Id'
