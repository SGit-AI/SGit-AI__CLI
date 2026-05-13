import time
from urllib.request                                        import urlopen, Request
from urllib.error                                          import URLError, HTTPError
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__Vault_Known(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='vault_known')

        if not ctx.vault_id:
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'no vault_id — run from inside a vault directory'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        vault_id = str(ctx.vault_id)
        url      = str(ctx.url).rstrip('/') + f'/api/vault/list/{vault_id}'
        headers  = {'Accept': 'application/json'}
        if ctx.token:
            headers['Authorization'] = f'Bearer {ctx.token}'

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=ctx.timeout_seconds) as resp:
                resp.read()
            result.status  = Enum__Doctor_Status.PASS
            result.message = f'vault {vault_id[:8]} exists on remote'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except HTTPError as e:
            if e.code == 404:
                result.status  = Enum__Doctor_Status.WARN
                result.message = f'vault {vault_id[:8]} not present on remote'
                result.hint    = (
                    'This is normal before the first push. The vault will be created\n'
                    '    when you run `sgit push`. To verify writes work end-to-end run:\n'
                    '      sgit doctor --write-probe'
                )
            else:
                result.status  = Enum__Doctor_Status.FAIL
                result.message = f'HTTP {e.code}: {e.reason}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except (URLError, OSError) as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'network error: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
