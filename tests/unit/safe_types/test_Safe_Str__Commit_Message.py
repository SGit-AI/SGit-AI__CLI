import pytest
from sg_send_cli.safe_types.Safe_Str__Commit_Message import Safe_Str__Commit_Message


class Test_Safe_Str__Commit_Message:

    def test_valid_message(self):
        msg = Safe_Str__Commit_Message('Add documentation files')
        assert msg == 'Add documentation files'

    def test_empty_allowed(self):
        msg = Safe_Str__Commit_Message('')
        assert msg == ''

    def test_with_newlines(self):
        msg = Safe_Str__Commit_Message('Line 1\nLine 2')
        assert msg == 'Line 1\nLine 2'

    def test_with_tabs(self):
        msg = Safe_Str__Commit_Message('item:\tvalue')
        assert msg == 'item:\tvalue'

    def test_max_length_accepted(self):
        msg = Safe_Str__Commit_Message('x' * 500)
        assert len(msg) == 500

    def test_over_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Commit_Message('x' * 501)

    def test_auto_generated_message_format(self):
        msg = Safe_Str__Commit_Message('Push: 2 added, 1 modified, 0 deleted')
        assert 'Push:' in msg

    def test_type_preserved(self):
        msg = Safe_Str__Commit_Message('test')
        assert type(msg).__name__ == 'Safe_Str__Commit_Message'
