import pytest
import base64
from sg_send_cli.safe_types.Safe_Str__Signature import Safe_Str__Signature


class Test_Safe_Str__Signature:

    def test_valid_base64_signature(self):
        sig = Safe_Str__Signature('dGVzdA==')
        assert sig == 'dGVzdA=='

    def test_valid_long_signature(self):
        raw = base64.b64encode(b'x' * 64).decode()
        sig = Safe_Str__Signature(raw)
        assert str(sig) == raw

    def test_empty_allowed(self):
        sig = Safe_Str__Signature('')
        assert sig == ''

    def test_invalid_chars_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Signature('invalid!@#$')

    def test_type_preserved(self):
        sig = Safe_Str__Signature('AAAA')
        assert type(sig).__name__ == 'Safe_Str__Signature'
