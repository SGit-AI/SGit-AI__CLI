import pytest
from sg_send_cli.safe_types.Safe_Str__Pending_Id import Safe_Str__Pending_Id


class Test_Safe_Str__Pending_Id:

    def test_valid_pending(self):
        pid = Safe_Str__Pending_Id('pending-1710412800000_a1b2c3d4')
        assert pid == 'pending-1710412800000_a1b2c3d4'

    def test_empty_allowed(self):
        pid = Safe_Str__Pending_Id('')
        assert pid == ''

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Pending_Id('pending-abc_def')

    def test_missing_random_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Pending_Id('pending-12345_')

    def test_type_preserved(self):
        pid = Safe_Str__Pending_Id('pending-12345_abcd1234')
        assert type(pid).__name__ == 'Safe_Str__Pending_Id'
