import io
import json
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from sgit_ai.cli.doctor.Check__API_Info     import Check__API_Info
from sgit_ai.cli.doctor.Doctor__Context     import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__API_Info:

    def _ctx(self, url='https://send.sgraph.ai'):
        return Doctor__Context(url=url, timeout_seconds=2)

    def _mock_response(self, body_dict):
        resp = MagicMock()
        resp.read = MagicMock(return_value=json.dumps(body_dict).encode())
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__  = MagicMock(return_value=False)
        return resp

    def test_pass_with_service_field(self):
        resp = self._mock_response({'service': 'sgraph-vault', 'version': 'v1.4.2'})
        with patch('sgit_ai.cli.doctor.Check__API_Info.urlopen', return_value=resp):
            check = Check__API_Info().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.PASS
        assert 'sgraph-vault' in str(check.message)
        assert 'v1.4.2'       in str(check.message)

    def test_warn_when_no_service_identifier(self):
        # 200 OK but body is missing the service field — server may be misconfigured.
        resp = self._mock_response({'other': 'thing'})
        with patch('sgit_ai.cli.doctor.Check__API_Info.urlopen', return_value=resp):
            check = Check__API_Info().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.WARN

    def test_404_degrades_to_warn(self):
        # Older servers without /api/info should degrade gracefully (not FAIL).
        err = HTTPError(url='', code=404, msg='Not Found', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__API_Info.urlopen', side_effect=err):
            check = Check__API_Info().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.WARN
        assert '404' in str(check.message) or 'not found' in str(check.message).lower()

    def test_5xx_fails(self):
        err = HTTPError(url='', code=503, msg='Service Unavailable', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__API_Info.urlopen', side_effect=err):
            check = Check__API_Info().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.FAIL
        assert '503' in str(check.message)

    def test_urlerror_fails(self):
        with patch('sgit_ai.cli.doctor.Check__API_Info.urlopen',
                   side_effect=URLError('Connection refused')):
            check = Check__API_Info().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'network error' in str(check.message)
