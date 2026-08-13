import io
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from sgit_ai.cli.doctor.Check__Write_Probe  import Check__Write_Probe
from sgit_ai.cli.doctor.Doctor__Context     import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__Write_Probe:

    def _ctx(self, write_probe=True, vault_id='abcd1234', token='tok-1'):
        return Doctor__Context(url='https://send.sgraph.ai',
                                vault_id=vault_id, token=token,
                                write_probe=write_probe, timeout_seconds=2)

    def test_skips_when_flag_off(self):
        check = Check__Write_Probe().execute(self._ctx(write_probe=False))
        assert check.status == Enum__Doctor_Status.SKIP
        assert 'pass --write-probe' in str(check.message)

    def test_skips_when_no_vault_id(self):
        check = Check__Write_Probe().execute(self._ctx(vault_id=None))
        assert check.status == Enum__Doctor_Status.SKIP

    def test_skips_when_no_token(self):
        check = Check__Write_Probe().execute(self._ctx(token=None))
        assert check.status == Enum__Doctor_Status.SKIP

    def test_passes_when_write_then_read_matches(self):
        # Write returns OK; read returns the same bytes we wrote; delete OK.
        write_resp = MagicMock()
        write_resp.__enter__ = MagicMock(return_value=write_resp)
        write_resp.__exit__  = MagicMock(return_value=False)

        # Capture the bytes written so the read mock returns the same payload.
        captured = {}
        def write_then_read(req, timeout=None):
            method = getattr(req, 'method', 'GET')
            if method == 'PUT':
                captured['payload'] = req.data
                return write_resp
            # GET (read) — return what was written
            read_resp = MagicMock()
            read_resp.read = MagicMock(return_value=captured.get('payload', b''))
            read_resp.__enter__ = MagicMock(return_value=read_resp)
            read_resp.__exit__  = MagicMock(return_value=False)
            return read_resp

        with patch('sgit_ai.cli.doctor.Check__Write_Probe.urlopen', side_effect=write_then_read):
            check = Check__Write_Probe().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.PASS
        assert 'round-trip' in str(check.message)

    def test_fails_when_read_back_mismatch(self):
        # Write OK but read returns different bytes — corruption or wrong file.
        def fake_urlopen(req, timeout=None):
            resp = MagicMock()
            resp.read = MagicMock(return_value=b'WRONG_DATA')
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__  = MagicMock(return_value=False)
            return resp
        with patch('sgit_ai.cli.doctor.Check__Write_Probe.urlopen', side_effect=fake_urlopen):
            check = Check__Write_Probe().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'mismatch' in str(check.message)

    def test_fails_on_http_error(self):
        err = HTTPError(url='', code=403, msg='Forbidden', hdrs=None, fp=io.BytesIO())
        with patch('sgit_ai.cli.doctor.Check__Write_Probe.urlopen', side_effect=err):
            check = Check__Write_Probe().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.FAIL
        assert '403' in str(check.message)
        # Orphan probe hint — token writes random ciphertext; user needs file_id to clean up.
        assert check.hint is not None
        assert 'Orphan' in str(check.hint)

    def test_fails_on_network_error(self):
        with patch('sgit_ai.cli.doctor.Check__Write_Probe.urlopen',
                   side_effect=URLError('refused')):
            check = Check__Write_Probe().execute(self._ctx())
        assert check.status == Enum__Doctor_Status.FAIL

    def test_probe_payload_is_random_not_vault_content(self):
        # Verify the probe writes random bytes (not vault content). This is the
        # zero-knowledge guarantee from the architect review §5.3.
        write_resp = MagicMock()
        write_resp.__enter__ = MagicMock(return_value=write_resp)
        write_resp.__exit__  = MagicMock(return_value=False)
        captured = {}
        def fake(req, timeout=None):
            method = getattr(req, 'method', 'GET')
            if method == 'PUT':
                captured['payload'] = req.data
                return write_resp
            r = MagicMock()
            r.read = MagicMock(return_value=captured.get('payload', b''))
            r.__enter__ = MagicMock(return_value=r)
            r.__exit__  = MagicMock(return_value=False)
            return r
        with patch('sgit_ai.cli.doctor.Check__Write_Probe.urlopen', side_effect=fake):
            Check__Write_Probe().execute(self._ctx())
        # The payload is 32 random bytes; should not match any well-known marker.
        assert captured['payload'] is not None
        assert len(captured['payload']) == 32
        assert b'sgit-doctor-probe' not in captured['payload']
