import pytest
from sg_send_cli.safe_types.Safe_Str__Secret_Key import Safe_Str__Secret_Key, SECRET_KEY__MAX_LENGTH


class Test_Safe_Str__Secret_Key__Boundary:

    def test_max_length_value(self):
        assert SECRET_KEY__MAX_LENGTH == 256

    def test_allow_empty_is_false(self):
        assert Safe_Str__Secret_Key.allow_empty is False

    def test_at_max_length_accepted(self):
        key = Safe_Str__Secret_Key('a' * 256)
        assert len(key) == 256

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Secret_Key('a' * 257)

    def test_dashes_allowed(self):
        key = Safe_Str__Secret_Key('my-api-key')
        assert key == 'my-api-key'

    def test_underscores_allowed(self):
        key = Safe_Str__Secret_Key('MY_SECRET_KEY')
        assert key == 'MY_SECRET_KEY'

    def test_dots_allowed(self):
        key = Safe_Str__Secret_Key('service.key.name')
        assert key == 'service.key.name'

    def test_spaces_sanitized(self):
        key = Safe_Str__Secret_Key('key with spaces')
        assert ' ' not in str(key)

    def test_at_sign_sanitized(self):
        key = Safe_Str__Secret_Key('key@value')
        assert '@' not in str(key)

    def test_slash_sanitized(self):
        key = Safe_Str__Secret_Key('key/value')
        assert '/' not in str(key)

    def test_colon_sanitized(self):
        key = Safe_Str__Secret_Key('key:value')
        assert ':' not in str(key)

    def test_type_preserved(self):
        key = Safe_Str__Secret_Key('test-key')
        assert type(key).__name__ == 'Safe_Str__Secret_Key'
