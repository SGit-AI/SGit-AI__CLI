import socket
import time
from urllib.parse                                          import urlparse
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check

LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


class Check__DNS_Resolve(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='dns_resolve')
        parsed = urlparse(str(ctx.url))
        host   = parsed.hostname or ''
        port   = parsed.port or (443 if parsed.scheme == 'https' else 80)

        if host in LOOPBACK_HOSTS or _is_ip(host):
            result.status      = Enum__Doctor_Status.PASS
            result.message     = 'literal IP, skipped'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        try:
            addrs = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            result.status      = Enum__Doctor_Status.PASS
            result.message     = f'{len(addrs)} address(es)'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except socket.gaierror as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f"DNS resolution failed for '{host}': {e.args[1] if e.args else e}"
            result.hint        = (f"Check the URL spelling: '{host}'\n"
                                  f"    • Test from your shell:  nslookup {host}\n"
                                  f"    • If this is an internal hostname, verify VPN / DNS search domains.")
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result


def _is_ip(host: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, host)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host.strip('[]'))
        return True
    except OSError:
        return False
