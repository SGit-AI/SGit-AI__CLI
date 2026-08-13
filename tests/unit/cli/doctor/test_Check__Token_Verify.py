import io
import json
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from sgit_ai.cli.doctor.Check__Token_Verify import Check__Token_Verify
from sgit_ai.cli.doctor.Doctor__Context     import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__Token_Verify:

    def _ctx(self, token=None, remote_name='origin'):
        return Doctor__Context(url='https://send.sgraph.ai', token=token,
                                timeout_seconds=2, remote_name=remote_name)

    def _mock_response(self, body_dict):
        resp = MagicMock()
        resp.read = MagicMock(return_value=json.dumps(body_dict).encode())
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__  = MagicMock(return_value=False)
        return resp

    def test_no_token_skips(self):
        check = Check__Token_Verify().execute(self._ctx(token=None))
        assert check.status == Enum__Doctor_Status.SKIP
        assert 'no token' in str(check.message)

    def test_pass_with_scopes(self):
        resp = self._mock_response({'scopes': ['read', 'write']})
        with patch('sgit_ai.cli.doctor.Check__Token_Verify.urlopen', return_value=resp):
            check = Check__Token_Verify().execute(self._ctx(token='good-token'))
        assert check.status == Enum__Doctor_Status.PASS
        assert 'read' in str(check.message)
        assert 'write' in str(check.message)

    def test_401_fails_with_recovery_hint(self):
        err = HTTPError(url='', code=401, msg='Unauthorized', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Token_Verify.urlopen', side_effect=err):
            check = Check__Token_Verify().execute(self._ctx(token='bad-token'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert '401' in str(check.message)
        assert check.hint is not None
        assert 'sgit auth' in str(check.hint)

    def test_403_fails(self):
        err = HTTPError(url='', code=403, msg='Forbidden', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Token_Verify.urlopen', side_effect=err):
            check = Check__Token_Verify().execute(self._ctx(token='wrong-scope'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert '403' in str(check.message)

    def test_404_degrades_to_warn(self):
        err = HTTPError(url='', code=404, msg='Not Found', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Token_Verify.urlopen', side_effect=err):
            check = Check__Token_Verify().execute(self._ctx(token='some-token'))
        assert check.status == Enum__Doctor_Status.WARN

    def test_network_error_fails(self):
        with patch('sgit_ai.cli.doctor.Check__Token_Verify.urlopen',
                   side_effect=URLError('Connection refused')):
            check = Check__Token_Verify().execute(self._ctx(token='some-token'))
        assert check.status == Enum__Doctor_Status.FAIL
