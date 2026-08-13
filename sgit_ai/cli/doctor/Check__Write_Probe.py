import os
import time
from urllib.request                                        import urlopen, Request
from urllib.error                                          import URLError, HTTPError
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check


class Check__Write_Probe(Type_Safe):

    def execute(self, ctx) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='write_probe')

        if not ctx.write_probe:
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'skipped (pass --write-probe to enable)'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        if not ctx.vault_id or not ctx.token:
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'skipped — vault_id or token missing'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        probe_suffix = os.urandom(6).hex()
        file_id      = f'obj-cas-imm-{probe_suffix}'
        probe_data   = os.urandom(32)            # random bytes — not vault content
        vault_id     = str(ctx.vault_id)
        base         = str(ctx.url).rstrip('/')
        write_url    = f'{base}/api/vault/write/{vault_id}/{file_id}'
        read_url     = f'{base}/api/vault/read/{vault_id}/{file_id}'
        delete_url   = f'{base}/api/vault/delete/{vault_id}/{file_id}'
        auth_header  = f'Bearer {ctx.token}'

        try:
            req = Request(write_url, data=probe_data, method='PUT',
                          headers={'Authorization': auth_header,
                                   'Content-Type': 'application/octet-stream'})
            with urlopen(req, timeout=ctx.timeout_seconds):
                pass

            req = Request(read_url, headers={'Authorization': auth_header})
            with urlopen(req, timeout=ctx.timeout_seconds) as resp:
                read_back = resp.read()

            if read_back != probe_data:
                result.status  = Enum__Doctor_Status.FAIL
                result.message = f'probe data mismatch — written {len(probe_data)}B, read back {len(read_back)}B'
                result.hint    = f'Orphan probe left on server: {file_id}'
                result.duration_ms = int((time.monotonic() - t0) * 1000)
                return result

            try:
                req = Request(delete_url, method='DELETE',
                              headers={'Authorization': auth_header})
                with urlopen(req, timeout=ctx.timeout_seconds):
                    pass
            except Exception:
                pass

            result.status      = Enum__Doctor_Status.PASS
            result.message     = f'round-trip ok ({len(probe_data)}B)'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        except HTTPError as e:
            result.status  = Enum__Doctor_Status.FAIL
            result.message = f'write probe failed: HTTP {e.code}'
            result.hint    = f'Orphan probe may be left on server: {file_id}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
        except (URLError, OSError) as e:
            result.status      = Enum__Doctor_Status.FAIL
            result.message     = f'write probe failed: {e}'
            result.duration_ms = int((time.monotonic() - t0) * 1000)

        return result
