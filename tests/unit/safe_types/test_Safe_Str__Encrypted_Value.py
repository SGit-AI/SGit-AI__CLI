import base64
import pytest
from sgit_ai.safe_types.Safe_Str__Encrypted_Value import Safe_Str__Encrypted_Value


class Test_Safe_Str__Encrypted_Value:

    def test_valid_base64(self):
        value = base64.b64encode(b'encrypted-data').decode()
        ev = Safe_Str__Encrypted_Value(value)
        assert str(ev) == value

    def test_empty_allowed(self):
        ev = Safe_Str__Encrypted_Value('')
        assert ev == ''

    def test_invalid_chars_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Encrypted_Value('not base64! @#$')

    def test_type_preserved(self):
        value = base64.b64encode(b'test').decode()
        ev = Safe_Str__Encrypted_Value(value)
        assert type(ev).__name__ == 'Safe_Str__Encrypted_Value'
