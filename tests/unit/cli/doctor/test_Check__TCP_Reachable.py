import socket
from unittest.mock import patch, MagicMock

from sgit_ai.cli.doctor.Check__TCP_Reachable import Check__TCP_Reachable
from sgit_ai.cli.doctor.Doctor__Context      import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status  import Enum__Doctor_Status


class Test_Check__TCP_Reachable:

    def _ctx(self, url, timeout=2):
        return Doctor__Context(url=url, timeout_seconds=timeout)

    def test_connection_succeeds(self):
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__  = MagicMock(return_value=False)
        with patch('socket.create_connection', return_value=mock_sock):
            check = Check__TCP_Reachable().execute(self._ctx('http://192.168.1.1:8080'))
        assert check.status     == Enum__Doctor_Status.PASS
        assert str(check.message) == 'connected'

    def test_connection_refused(self):
        with patch('socket.create_connection', side_effect=ConnectionRefusedError()):
            check = Check__TCP_Reachable().execute(self._ctx('http://0.0.0.0:8080'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'refused' in str(check.message)
        assert '0.0.0.0:8080' in str(check.message)

    def test_timeout(self):
        with patch('socket.create_connection', side_effect=socket.timeout()):
            check = Check__TCP_Reachable().execute(self._ctx('http://slow.example:443'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'timed out' in str(check.message)
        assert check.hint is not None

    def test_generic_oserror(self):
        with patch('socket.create_connection', side_effect=OSError('Network unreachable')):
            check = Check__TCP_Reachable().execute(self._ctx('http://9.9.9.9:8080'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'network error' in str(check.message)

    def test_uses_correct_port_for_https(self):
        captured = {}
        def fake_conn(addr, timeout=None):
            captured['addr'] = addr
            captured['timeout'] = timeout
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__  = MagicMock(return_value=False)
            return mock
        with patch('socket.create_connection', side_effect=fake_conn):
            Check__TCP_Reachable().execute(self._ctx('https://example.com'))
        assert captured['addr'] == ('example.com', 443)
        assert captured['timeout'] == 2
