import json
import time
from urllib.request                                        import urlopen, Request
from urllib.error                                          import URLError, HTTPError
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__Token_Verify(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='token_verify')

        if not ctx.token:
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'no token configured — skipped'
            result.hint        = 'Pass --token or run: sgit auth'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        url = str(ctx.url).rstrip('/') + '/api/auth/whoami'
        try:
            req = Request(url, headers={
                'Accept':        'application/json',
                'Authorization': f'Bearer {ctx.token}',
            })
            with urlopen(req, timeout=ctx.timeout_seconds) as resp:
                body   = json.loads(resp.read().decode())
            scopes = body.get('scopes', [])
            scope_str = ', '.join(scopes) if scopes else 'unknown'
            result.status  = Enum__Doctor_Status.PASS
            result.message = f'ok — scope: {scope_str}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except HTTPError as e:
            if e.code in (401, 403):
                base = str(ctx.url).rstrip('/')
                result.status  = Enum__Doctor_Status.FAIL
                result.message = f'HTTP {e.code} — token rejected'
                result.hint    = (
                    f'• Verify your token at:  {base}/account/tokens\n'
                    f'    • Save a new token:      sgit auth --remote {ctx.remote_name}'
                )
            elif e.code == 404:
                result.status  = Enum__Doctor_Status.WARN
                result.message = '/api/auth/whoami not found — older server (degraded gracefully)'
            else:
                result.status  = Enum__Doctor_Status.FAIL
                result.message = f'HTTP {e.code}: {e.reason}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except (URLError, OSError) as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'network error: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
