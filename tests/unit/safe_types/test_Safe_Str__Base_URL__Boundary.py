import pytest
from sg_send_cli.safe_types.Safe_Str__Base_URL import Safe_Str__Base_URL, BASE_URL__MAX_LENGTH


class Test_Safe_Str__Base_URL__Boundary:

    def test_max_length_value(self):
        assert BASE_URL__MAX_LENGTH == 2048

    def test_at_max_length_accepted(self):
        url = Safe_Str__Base_URL('https://example.com/' + 'a' * (2048 - 20))
        assert len(url) == 2048

    def test_exceeds_max_length_rejected(self):
        with pytest.raises(ValueError):
            Safe_Str__Base_URL('a' * 2049)

    def test_https_url_accepted(self):
        url = Safe_Str__Base_URL('https://send.sgraph.ai')
        assert url == 'https://send.sgraph.ai'

    def test_http_url_accepted(self):
        url = Safe_Str__Base_URL('http://localhost:8080')
        assert url == 'http://localhost:8080'

    def test_url_with_port_accepted(self):
        url = Safe_Str__Base_URL('https://api.example.com:443')
        assert ':443' in str(url)

    def test_url_with_path_accepted(self):
        url = Safe_Str__Base_URL('https://api.example.com/v1/transfer')
        assert '/v1/transfer' in str(url)

    def test_javascript_protocol_sanitized(self):
        url = Safe_Str__Base_URL('javascript:alert(1)')
        assert 'javascript' not in str(url).lower() or '(' not in str(url)

    def test_spaces_sanitized(self):
        url = Safe_Str__Base_URL('https://example.com/ path')
        assert ' ' not in str(url)

    def test_angle_brackets_sanitized(self):
        url = Safe_Str__Base_URL('https://example.com/<script>')
        assert '<' not in str(url)
        assert '>' not in str(url)

    def test_semicolon_sanitized(self):
        url = Safe_Str__Base_URL('https://example.com;evil')
        assert ';' not in str(url)

    def test_empty_allowed(self):
        url = Safe_Str__Base_URL('')
        assert url == ''

    def test_none_gives_empty(self):
        url = Safe_Str__Base_URL(None)
        assert url == ''

    def test_type_preserved(self):
        url = Safe_Str__Base_URL('https://example.com')
        assert type(url).__name__ == 'Safe_Str__Base_URL'
