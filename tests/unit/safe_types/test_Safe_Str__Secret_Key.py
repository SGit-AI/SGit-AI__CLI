from sgit_ai.safe_types.Safe_Str__Secret_Key import Safe_Str__Secret_Key


class Test_Safe_Str__Secret_Key:

    def test_accepts_valid_key(self):
        k = Safe_Str__Secret_Key('x')
        k.value = 'my-api-key'
        assert k.value == 'my-api-key'

    def test_accepts_dotted_key(self):
        k = Safe_Str__Secret_Key('x')
        k.value = 'service.api.token'
        assert k.value == 'service.api.token'

    def test_accepts_underscored_key(self):
        k = Safe_Str__Secret_Key('x')
        k.value = 'AWS_SECRET_KEY'
        assert k.value == 'AWS_SECRET_KEY'

    def test_max_length(self):
        k = Safe_Str__Secret_Key('x')
        assert k.max_length == 256

    def test_type_preserved(self):
        k = Safe_Str__Secret_Key('x')
        k.value = 'test-key'
        assert isinstance(k, Safe_Str__Secret_Key)
