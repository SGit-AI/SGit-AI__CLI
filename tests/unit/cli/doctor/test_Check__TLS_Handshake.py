import ssl
from unittest.mock import patch, MagicMock

from sgit_ai.cli.doctor.Check__TLS_Handshake import Check__TLS_Handshake
from sgit_ai.cli.doctor.Doctor__Context      import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status  import Enum__Doctor_Status


class Test_Check__TLS_Handshake:

    def _ctx(self, url, tls_verify=True):
        return Doctor__Context(url=url, timeout_seconds=2, tls_verify=tls_verify)

    def test_http_scheme_skips(self):
        # No TLS to handshake when scheme is plain http.
        check = Check__TLS_Handshake().execute(self._ctx('http://example.com'))
        assert check.status == Enum__Doctor_Status.SKIP
        assert 'n/a' in str(check.message)

    def test_successful_handshake(self):
        # Mock both socket.create_connection and ssl context.wrap_socket.
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__  = MagicMock(return_value=False)
        mock_ssl = MagicMock()
        mock_ssl.__enter__ = MagicMock(return_value=mock_ssl)
        mock_ssl.__exit__  = MagicMock(return_value=False)
        with patch('socket.create_connection', return_value=mock_sock), \
             patch('ssl.create_default_context') as fake_ctx:
            fake_ctx.return_value.wrap_socket.return_value = mock_ssl
            check = Check__TLS_Handshake().execute(self._ctx('https://example.com'))
        assert check.status == Enum__Doctor_Status.PASS

    def test_certificate_verify_failed_has_recovery_hint(self):
        # ssl.SSLCertVerificationError is the specific error we surface with extra advice.
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__  = MagicMock(return_value=False)
        cert_err = ssl.SSLCertVerificationError(1, 'self signed certificate')
        cert_err.reason = 'self signed certificate'
        with patch('socket.create_connection', return_value=mock_sock), \
             patch('ssl.create_default_context') as fake_ctx:
            fake_ctx.return_value.wrap_socket.side_effect = cert_err
            check = Check__TLS_Handshake().execute(self._ctx('https://self-signed.local'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'certificate verify failed' in str(check.message)
        assert check.hint is not None
        assert '--no-verify-tls' in str(check.hint)

    def test_tls_verify_off_disables_verification(self):
        # When tls_verify=False we expect CERT_NONE on the context.
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__  = MagicMock(return_value=False)
        mock_wrapped = MagicMock()
        mock_wrapped.__enter__ = MagicMock(return_value=mock_wrapped)
        mock_wrapped.__exit__  = MagicMock(return_value=False)
        with patch('socket.create_connection', return_value=mock_sock), \
             patch('ssl.create_default_context') as fake_ctx:
            fake_ctx.return_value.wrap_socket.return_value = mock_wrapped
            Check__TLS_Handshake().execute(self._ctx('https://x.example', tls_verify=False))
            ctx = fake_ctx.return_value
            assert ctx.check_hostname is False
            assert ctx.verify_mode    == ssl.CERT_NONE

    def test_generic_oserror(self):
        with patch('socket.create_connection', side_effect=OSError('Connection reset')):
            check = Check__TLS_Handshake().execute(self._ctx('https://x.example'))
        assert check.status == Enum__Doctor_Status.FAIL
