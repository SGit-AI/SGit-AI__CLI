import pytest
from sg_send_cli.safe_types.Safe_Str__File_Id import Safe_Str__File_Id


class Test_Safe_Str__File_Id:

    def test_valid_file_id(self):
        fid = Safe_Str__File_Id('4bc7e18f0779')
        assert fid == '4bc7e18f0779'

    def test_valid_file_id_all_digits(self):
        fid = Safe_Str__File_Id('123456789012')
        assert fid == '123456789012'

    def test_empty_allowed(self):
        fid = Safe_Str__File_Id('')
        assert fid == ''

    def test_uppercase_converted_to_lower(self):
        fid = Safe_Str__File_Id('4BC7E18F0779')
        assert fid == '4bc7e18f0779'

    def test_too_short_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__File_Id('4bc7e18f')

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__File_Id('4bc7e18f077900')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__File_Id('4bc7e18f077z')

    def test_type_preserved(self):
        fid = Safe_Str__File_Id('4bc7e18f0779')
        assert type(fid).__name__ == 'Safe_Str__File_Id'
