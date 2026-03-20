import pytest
from sgit_ai.safe_types.Safe_Str__Index_Id import Safe_Str__Index_Id


class Test_Safe_Str__Index_Id:

    def test_valid_index(self):
        iid = Safe_Str__Index_Id('idx-pid-muw-a1b2c3d4e5f6')
        assert iid == 'idx-pid-muw-a1b2c3d4e5f6'

    def test_empty_allowed(self):
        iid = Safe_Str__Index_Id('')
        assert iid == ''

    def test_invalid_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Index_Id('index-a1b2c3d4')

    def test_old_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Index_Id('idx-a1b2c3d4')

    def test_type_preserved(self):
        iid = Safe_Str__Index_Id('idx-pid-muw-deadbeefcafe')
        assert type(iid).__name__ == 'Safe_Str__Index_Id'
