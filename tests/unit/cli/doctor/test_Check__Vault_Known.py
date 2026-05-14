import io
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from sgit_ai.cli.doctor.Check__Vault_Known  import Check__Vault_Known
from sgit_ai.cli.doctor.Doctor__Context     import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__Vault_Known:

    def _ctx(self, vault_id=None, token=None):
        return Doctor__Context(url='https://send.sgraph.ai',
                                vault_id=vault_id, token=token, timeout_seconds=2)

    def _mock_ok_response(self):
        resp = MagicMock()
        resp.read = MagicMock(return_value=b'[]')
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__  = MagicMock(return_value=False)
        return resp

    def test_no_vault_id_skips(self):
        check = Check__Vault_Known().execute(self._ctx(vault_id=None))
        assert check.status == Enum__Doctor_Status.SKIP

    def test_pass_when_vault_exists(self):
        with patch('sgit_ai.cli.doctor.Check__Vault_Known.urlopen',
                   return_value=self._mock_ok_response()):
            check = Check__Vault_Known().execute(self._ctx(vault_id='a1b2c3d4'))
        assert check.status == Enum__Doctor_Status.PASS
        assert 'a1b2c3d4' in str(check.message)

    def test_warn_on_404_with_first_push_hint(self):
        # 404 is expected on first push; we WARN (not FAIL) and explain.
        err = HTTPError(url='', code=404, msg='Not Found', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Vault_Known.urlopen', side_effect=err):
            check = Check__Vault_Known().execute(self._ctx(vault_id='abcd1234'))
        assert check.status == Enum__Doctor_Status.WARN
        assert 'not present' in str(check.message)
        assert check.hint is not None
        assert 'first push' in str(check.hint)

    def test_5xx_fails(self):
        err = HTTPError(url='', code=500, msg='Server Error', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Vault_Known.urlopen', side_effect=err):
            check = Check__Vault_Known().execute(self._ctx(vault_id='abcd1234'))
        assert check.status == Enum__Doctor_Status.FAIL

    def test_network_error_fails(self):
        with patch('sgit_ai.cli.doctor.Check__Vault_Known.urlopen',
                   side_effect=URLError('refused')):
            check = Check__Vault_Known().execute(self._ctx(vault_id='abcd1234'))
        assert check.status == Enum__Doctor_Status.FAIL

    def test_authorization_header_included_when_token(self):
        captured_req = {}
        def fake_urlopen(req, timeout=None):
            captured_req['headers'] = dict(req.headers)
            return self._mock_ok_response()
        with patch('sgit_ai.cli.doctor.Check__Vault_Known.urlopen', side_effect=fake_urlopen):
            Check__Vault_Known().execute(self._ctx(vault_id='abc', token='tok-xyz'))
        # Header names get title-cased by urllib
        assert any('tok-xyz' in v for v in captured_req['headers'].values())
