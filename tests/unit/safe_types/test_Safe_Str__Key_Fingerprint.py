import pytest
from sg_send_cli.safe_types.Safe_Str__Key_Fingerprint import Safe_Str__Key_Fingerprint


class Test_Safe_Str__Key_Fingerprint:

    def test_accepts_valid_fingerprint(self):
        fp = Safe_Str__Key_Fingerprint('sha256:a1b2c3d4e5f6a7b8')
        assert str(fp) == 'sha256:a1b2c3d4e5f6a7b8'

    def test_accepts_empty(self):
        fp = Safe_Str__Key_Fingerprint('')
        assert str(fp) == ''

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Fingerprint('md5:a1b2c3d4e5f6a7b8')

    def test_rejects_wrong_length(self):
        with pytest.raises(ValueError):
            Safe_Str__Key_Fingerprint('sha256:a1b2c3')

    def test_uppercase_converted_to_lowercase(self):
        fp = Safe_Str__Key_Fingerprint('sha256:A1B2C3D4E5F6A7B8')
        assert str(fp) == 'sha256:a1b2c3d4e5f6a7b8'

    def test_format_is_23_chars(self):
        fp = Safe_Str__Key_Fingerprint('sha256:0123456789abcdef')
        assert len(str(fp)) == 23
