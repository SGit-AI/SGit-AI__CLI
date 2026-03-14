import pytest
from sg_send_cli.safe_types.Safe_Str__Index_Id import Safe_Str__Index_Id


class Test_Safe_Str__Index_Id:

    def test_valid_index(self):
        iid = Safe_Str__Index_Id('idx-a1b2c3d4')
        assert iid == 'idx-a1b2c3d4'

    def test_empty_allowed(self):
        iid = Safe_Str__Index_Id('')
        assert iid == ''

    def test_invalid_prefix_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Index_Id('index-a1b2c3d4')

    def test_type_preserved(self):
        iid = Safe_Str__Index_Id('idx-deadbeef')
        assert type(iid).__name__ == 'Safe_Str__Index_Id'
