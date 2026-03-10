import pytest
from sg_send_cli.safe_types.Safe_Str__Object_Id import Safe_Str__Object_Id


class Test_Safe_Str__Object_Id:

    def test_valid_object_id(self):
        oid = Safe_Str__Object_Id('a1b2c3d4e5f6')
        assert oid == 'a1b2c3d4e5f6'

    def test_valid_all_digits(self):
        oid = Safe_Str__Object_Id('123456789012')
        assert oid == '123456789012'

    def test_empty_allowed(self):
        oid = Safe_Str__Object_Id('')
        assert oid == ''

    def test_uppercase_converted_to_lower(self):
        oid = Safe_Str__Object_Id('A1B2C3D4E5F6')
        assert oid == 'a1b2c3d4e5f6'

    def test_too_short_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Object_Id('a1b2c3')

    def test_too_long_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Object_Id('a1b2c3d4e5f600')

    def test_non_hex_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Object_Id('a1b2c3d4e5gz')

    def test_type_preserved(self):
        oid = Safe_Str__Object_Id('a1b2c3d4e5f6')
        assert type(oid).__name__ == 'Safe_Str__Object_Id'

    def test_distinct_from_file_id(self):
        from sg_send_cli.safe_types.Safe_Str__File_Id import Safe_Str__File_Id
        oid = Safe_Str__Object_Id('a1b2c3d4e5f6')
        fid = Safe_Str__File_Id('a1b2c3d4e5f6')
        assert type(oid) != type(fid)
