import pytest
from sg_send_cli.safe_types.Safe_Str__Transfer_Id import Safe_Str__Transfer_Id


class Test_Safe_Str__Transfer_Id:

    def test_valid_transfer_id(self):
        tid = Safe_Str__Transfer_Id('abc123def456')
        assert tid == 'abc123def456'

    def test_whitespace_trimmed(self):
        tid = Safe_Str__Transfer_Id('  abc123def456  ')
        assert tid == 'abc123def456'

    def test_empty_allowed(self):
        tid = Safe_Str__Transfer_Id('')
        assert tid == ''

    def test_wrong_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Transfer_Id('abc123')

    def test_special_chars_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Transfer_Id('abc-123-def!')

    def test_type_preserved(self):
        tid = Safe_Str__Transfer_Id('abc123def456')
        assert type(tid).__name__ == 'Safe_Str__Transfer_Id'
