import socket
import ssl
import time
from urllib.parse                                          import urlparse
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__TLS_Handshake(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='tls_handshake')
        parsed = urlparse(str(ctx.url))

        if parsed.scheme != 'https':
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'n/a (http)'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        host = parsed.hostname or ''
        port = parsed.port or 443

        try:
            ctx_ssl = ssl.create_default_context()
            if not ctx.tls_verify:
                ctx_ssl.check_hostname = False
                ctx_ssl.verify_mode    = ssl.CERT_NONE
            with socket.create_connection((host, port), timeout=ctx.timeout_seconds) as sock:
                with ctx_ssl.wrap_socket(sock, server_hostname=host):
                    pass
            result.status      = Enum__Doctor_Status.PASS
            result.message     = 'ok, cert valid'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except ssl.SSLCertVerificationError as e:
            result.status  = Enum__Doctor_Status.FAIL
            result.message = f'certificate verify failed: {e.reason}'
            result.hint    = (
                'This usually means one of:\n'
                '    • The server has a self-signed certificate\n'
                '    • Your CA bundle is out of date (try: pip install --upgrade certifi)\n'
                '    • The server hostname does not match the certificate\n\n'
                '    If you trust this server, opt out of TLS verification for this remote ONLY:\n'
                '      sgit vault remote add <name> <url> --no-verify-tls\n\n'
                '    NOTE: --no-verify-tls weakens transport security. Vault contents remain\n'
                '    end-to-end encrypted regardless, but a network attacker can observe\n'
                '    vault_id, file_id, and timing.'
            )
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except ssl.SSLError as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'TLS handshake failed: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except OSError as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'connection error during TLS: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
