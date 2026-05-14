import socket
from unittest.mock import patch

from sgit_ai.cli.doctor.Check__DNS_Resolve import Check__DNS_Resolve
from sgit_ai.cli.doctor.Doctor__Context    import Doctor__Context
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status


class Test_Check__DNS_Resolve:

    def _ctx(self, url):
        return Doctor__Context(url=url, timeout_seconds=2)

    def test_loopback_skipped(self):
        # Loopback hosts skip the DNS step (no resolution needed).
        check = Check__DNS_Resolve().execute(self._ctx('http://localhost:8080'))
        assert check.status     == Enum__Doctor_Status.PASS
        assert 'skipped' in str(check.message).lower() or 'literal IP' in str(check.message)

    def test_ipv4_literal_skipped(self):
        check = Check__DNS_Resolve().execute(self._ctx('http://192.168.1.1:8080'))
        assert check.status == Enum__Doctor_Status.PASS
        assert 'literal IP' in str(check.message)

    def test_resolvable_host_returns_count(self):
        with patch('socket.getaddrinfo',
                   return_value=[('AF_INET', None, None, '', ('1.1.1.1', 443))]):
            check = Check__DNS_Resolve().execute(self._ctx('https://example.com'))
        assert check.status == Enum__Doctor_Status.PASS
        assert 'address' in str(check.message)

    def test_unresolvable_host_fails_with_hint(self):
        with patch('socket.getaddrinfo',
                   side_effect=socket.gaierror(-2, 'Name or service not known')):
            check = Check__DNS_Resolve().execute(self._ctx('https://no-such-host.invalid'))
        assert check.status == Enum__Doctor_Status.FAIL
        assert 'no-such-host.invalid' in str(check.message)
        assert check.hint is not None
        assert 'nslookup' in str(check.hint)

    def test_duration_recorded(self):
        check = Check__DNS_Resolve().execute(self._ctx('http://localhost:80'))
        assert check.duration_ms is not None

    def test_is_ip_literal_method(self):
        c = Check__DNS_Resolve()
        assert c.is_ip_literal('127.0.0.1') is True
        assert c.is_ip_literal('192.168.1.42') is True
        assert c.is_ip_literal('::1') is True
        assert c.is_ip_literal('example.com') is False
        assert c.is_ip_literal('not-an-ip-at-all') is False
