import ssl
from urllib.error import URLError
from sg_send_cli.cli.CLI__Main import CLI__Main


class Test_CLI__Main__SSL:

    def test_check_ssl_error_detects_certificate_failure(self):
        cli   = CLI__Main()
        inner = ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')
        outer = URLError(inner)
        hint  = cli._check_ssl_error(outer)
        assert 'SSL Error' in hint
        assert 'certifi' in hint

    def test_check_ssl_error_ignores_non_ssl(self):
        cli  = CLI__Main()
        hint = cli._check_ssl_error(RuntimeError('something else'))
        assert hint == ''

    def test_check_ssl_error_detects_nested_ssl(self):
        cli   = CLI__Main()
        inner = ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')
        mid   = URLError(inner)
        outer = RuntimeError('wrapped')
        outer.__cause__ = mid
        hint  = cli._check_ssl_error(outer)
        assert 'SSL Error' in hint

    def test_check_ssl_error_detects_string_match(self):
        cli  = CLI__Main()
        err  = URLError('CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate')
        hint = cli._check_ssl_error(err)
        assert 'SSL Error' in hint
