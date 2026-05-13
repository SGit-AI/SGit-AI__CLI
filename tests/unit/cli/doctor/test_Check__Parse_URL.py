from sgit_ai.cli.doctor.Check__Parse_URL    import Check__Parse_URL
from sgit_ai.cli.doctor.Doctor__Context     import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__Parse_URL:

    def _ctx(self, url):
        return Doctor__Context(url=url)

    def test_valid_https(self):
        check = Check__Parse_URL().execute(self._ctx('https://send.sgraph.ai'))
        assert check.status == Enum__Doctor_Status.PASS
        assert 'https' in str(check.message)
        assert 'send.sgraph.ai' in str(check.message)

    def test_valid_http_with_port(self):
        check = Check__Parse_URL().execute(self._ctx('http://localhost:8080'))
        assert check.status == Enum__Doctor_Status.PASS

    def test_no_url(self):
        check = Check__Parse_URL().execute(Doctor__Context())
        assert check.status == Enum__Doctor_Status.FAIL

    def test_bad_scheme(self):
        check = Check__Parse_URL().execute(self._ctx('ftp://example.com'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'scheme' in str(check.message).lower()

    def test_duration_recorded(self):
        check = Check__Parse_URL().execute(self._ctx('https://send.sgraph.ai'))
        assert check.duration_ms is not None
