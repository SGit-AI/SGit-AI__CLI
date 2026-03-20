from sgit_ai.safe_types.Safe_Str__Base_URL import Safe_Str__Base_URL


class Test_Safe_Str__Base_URL:

    def test_accepts_valid_https_url(self):
        url = Safe_Str__Base_URL()
        url.value = 'https://send.sgraph.ai'
        assert url.value == 'https://send.sgraph.ai'

    def test_accepts_valid_http_url(self):
        url = Safe_Str__Base_URL()
        url.value = 'http://localhost:8080'
        assert url.value == 'http://localhost:8080'

    def test_accepts_empty(self):
        url = Safe_Str__Base_URL()
        url.value = ''
        assert url.value == ''

    def test_max_length(self):
        url = Safe_Str__Base_URL()
        assert url.max_length == 2048

    def test_type_preserved(self):
        url = Safe_Str__Base_URL()
        url.value = 'https://example.com'
        assert isinstance(url, Safe_Str__Base_URL)
