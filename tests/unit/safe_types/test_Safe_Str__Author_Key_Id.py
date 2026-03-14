import pytest
from sg_send_cli.safe_types.Safe_Str__Author_Key_Id import Safe_Str__Author_Key_Id


class Test_Safe_Str__Author_Key_Id:

    def test_valid_fingerprint_style(self):
        akid = Safe_Str__Author_Key_Id('sha256:a1b2c3d4e5f6a7b8')
        assert akid == 'sha256:a1b2c3d4e5f6a7b8'

    def test_valid_simple(self):
        akid = Safe_Str__Author_Key_Id('user-key-1')
        assert akid == 'user-key-1'

    def test_empty_allowed(self):
        akid = Safe_Str__Author_Key_Id('')
        assert akid == ''

    def test_type_preserved(self):
        akid = Safe_Str__Author_Key_Id('my_key')
        assert type(akid).__name__ == 'Safe_Str__Author_Key_Id'
