import pytest
from sg_send_cli.safe_types.Safe_Str__Content_Type import Safe_Str__Content_Type


class Test_Safe_Str__Content_Type:

    def test_valid_content_type(self):
        ct = Safe_Str__Content_Type('application/octet-stream')
        assert ct == 'application/octet-stream'

    def test_text_markdown(self):
        ct = Safe_Str__Content_Type('text/markdown')
        assert ct == 'text/markdown'

    def test_json_type(self):
        ct = Safe_Str__Content_Type('application/json')
        assert ct == 'application/json'

    def test_with_plus(self):
        ct = Safe_Str__Content_Type('application/vnd.api+json')
        assert ct == 'application/vnd.api+json'

    def test_empty_allowed(self):
        ct = Safe_Str__Content_Type('')
        assert ct == ''

    def test_type_preserved(self):
        ct = Safe_Str__Content_Type('text/plain')
        assert type(ct).__name__ == 'Safe_Str__Content_Type'
