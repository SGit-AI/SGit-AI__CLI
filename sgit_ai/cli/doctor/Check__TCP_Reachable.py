import socket
import time
from urllib.parse                                          import urlparse
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check

LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


class Check__TCP_Reachable(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='tcp_reachable')
        parsed = urlparse(str(ctx.url))
        host   = parsed.hostname or ''
        port   = parsed.port or (443 if parsed.scheme == 'https' else 80)

        try:
            with socket.create_connection((host, port), timeout=ctx.timeout_seconds):
                pass
            result.status      = Enum__Doctor_Status.PASS
            result.message     = 'connected'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except ConnectionRefusedError:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'connection refused at {host}:{port}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except socket.timeout:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'timed out after {ctx.timeout_seconds}s connecting to {host}:{port}'
            result.hint        = 'Check firewall rules or try increasing --timeout'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except OSError as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'network error: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
