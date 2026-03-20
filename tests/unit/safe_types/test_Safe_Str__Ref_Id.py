import pytest
from sgit_ai.safe_types.Safe_Str__Ref_Id import Safe_Str__Ref_Id


class Test_Safe_Str__Ref_Id:

    def test_valid_ref_muw(self):
        rid = Safe_Str__Ref_Id('ref-pid-muw-a1b2c3d4e5f6')
        assert rid == 'ref-pid-muw-a1b2c3d4e5f6'

    def test_valid_ref_snw(self):
        rid = Safe_Str__Ref_Id('ref-pid-snw-a1b2c3d4e5f6')
        assert rid == 'ref-pid-snw-a1b2c3d4e5f6'

    def test_empty_allowed(self):
        rid = Safe_Str__Ref_Id('')
        assert rid == ''

    def test_uppercase_lowered(self):
        rid = Safe_Str__Ref_Id('ref-pid-muw-AABB11223344')
        assert rid == 'ref-pid-muw-aabb11223344'

    def test_missing_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Ref_Id('a1b2c3d4e5f6')

    def test_old_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Ref_Id('ref-a1b2c3d4e5f6')

    def test_type_preserved(self):
        rid = Safe_Str__Ref_Id('ref-pid-muw-a1b2c3d4e5f6')
        assert type(rid).__name__ == 'Safe_Str__Ref_Id'
