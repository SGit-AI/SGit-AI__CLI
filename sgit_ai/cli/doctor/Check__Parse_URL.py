import time
from urllib.parse                                          import urlparse
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__Parse_URL(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        url    = str(ctx.url) if ctx.url else ''
        result = Schema__Doctor__Check(name='parse_url')

        if not url:
            result.status  = Enum__Doctor_Status.FAIL
            result.message = 'No URL configured'
            result.hint    = 'Set a remote URL with: sgit vault remote add origin <url>'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            result.status  = Enum__Doctor_Status.FAIL
            result.message = f"URL scheme must be 'http' or 'https', got: '{parsed.scheme}'"
            result.hint    = f'Try: https://{url.lstrip(":/")}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        if not parsed.hostname:
            result.status  = Enum__Doctor_Status.FAIL
            result.message = f'URL has no hostname: {url}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        port    = parsed.port or (443 if parsed.scheme == 'https' else 80)
        summary = f'valid ({parsed.scheme}, {parsed.hostname}, {port})'

        result.status      = Enum__Doctor_Status.PASS
        result.message     = summary
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result
