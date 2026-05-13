import json
import time
from urllib.request                                        import urlopen, Request
from urllib.error                                          import URLError, HTTPError
from urllib.parse                                          import urljoin
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__API_Info(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='api_info')
        url    = str(ctx.url).rstrip('/') + '/api/info'

        try:
            req  = Request(url, headers={'Accept': 'application/json'})
            with urlopen(req, timeout=ctx.timeout_seconds) as resp:
                body = json.loads(resp.read().decode())
            service = body.get('service', '')
            version = body.get('version', '')
            if service:
                result.status  = Enum__Doctor_Status.PASS
                result.message = f'{service} {version}'.strip()
            else:
                result.status  = Enum__Doctor_Status.WARN
                result.message = 'endpoint returned 200 but no service identifier'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except HTTPError as e:
            if e.code == 404:
                result.status  = Enum__Doctor_Status.WARN
                result.message = '/api/info not found — older server (degraded gracefully)'
                result.hint    = 'The server may not support /api/info. Core operations still work.'
            else:
                result.status  = Enum__Doctor_Status.FAIL
                result.message = f'HTTP {e.code}: {e.reason}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except (URLError, OSError) as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'network error: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
