import base64
import http.client
import io
import json
import os
import ssl
import threading
import time
from   urllib.parse                                  import quote
from   urllib.error                                  import HTTPError, URLError
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.safe_types.Safe_Str__Base_URL     import Safe_Str__Base_URL
from   sgit_ai.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token

TRANSIENT_STATUS_CODES = {429, 502, 503, 504}   # 429: throttled — back off and retry like a 5xx
RETRY_DELAYS           = [2, 4, 8]            # seconds between attempts

DEFAULT_BASE_URL       = 'https://dev.send.sgraph.ai'
LARGE_BLOB_THRESHOLD   = 4 * 1024 * 1024   # 4 MB — safe margin under Lambda base64 limit (~4.7 MB)
MAX_BATCH_OPS          = 50                 # conservative margin under server's 100-op hard limit
BATCH_READ_WORKERS     = 16                 # parallel chunks per batch_read (measured: ~2x the throughput of 8 on the live API)
_POOL_INIT_LOCK        = threading.Lock()   # guards the lazy creation of a Vault__API's connection pool


class Vault__API(Type_Safe):
    base_url     : Safe_Str__Base_URL     = None
    access_token : Safe_Str__Access_Token = None
    tls_verify   : bool                   = True
    debug_log    : object                 = None
    http_pool    : object                 = None   # Vault__HTTP_Pool, built on first request

    def setup(self):
        if not self.base_url:
            self.base_url = self.default_base_url()
        return self

    def default_base_url(self) -> str:
        """The server used when none is configured: SGIT_DEFAULT_BASE_URL (a self-hosted
        default, or a test sandbox) else DEFAULT_BASE_URL."""
        return os.environ.get('SGIT_DEFAULT_BASE_URL') or DEFAULT_BASE_URL

    def _auth_headers(self, extra: dict = None) -> dict:
        # New-style vault-app stacks (v0.2.6+) put a FastAPI middleware in front
        # of the vault app that checks X-API-Key; the vault app itself still
        # checks x-sgraph-access-token. Both env vars are set to the same value
        # at create time, so we send the token on both header names.
        headers = {}
        if self.access_token:
            token                          = str(self.access_token)
            headers['x-sgraph-access-token'] = token
            headers['X-API-Key']             = token
        if extra:
            headers.update(extra)
        return headers

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        url     = f'{self.base_url}/api/vault/write/{vault_id}/{quote(file_id, safe="")}'
        headers = self._auth_headers({'Content-Type'             : 'application/octet-stream',
                                       'x-sgraph-vault-write-key' : write_key})
        return self._request('PUT', url, headers, payload)

    def read(self, vault_id: str, file_id: str) -> bytes:
        url     = f'{self.base_url}/api/vault/read/{vault_id}/{quote(file_id, safe="")}'
        return self._request_bytes('GET', url, self._auth_headers())

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        url     = f'{self.base_url}/api/vault/delete/{vault_id}/{quote(file_id, safe="")}'
        headers = self._auth_headers({'x-sgraph-vault-write-key' : write_key})
        return self._request('DELETE', url, headers)

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Execute a batch of operations atomically.

        Each operation is a dict with:
            op      : 'write' | 'write-if-match' | 'delete' | 'read'
            file_id : str
            data    : base64-encoded bytes (for write ops)
            match   : SHA256 hash of current content (for write-if-match)

        Returns dict with status and per-operation results.
        If any write-if-match fails, the entire batch is rejected.
        """
        url     = f'{self.base_url}/api/vault/batch/{vault_id}'
        headers = self._auth_headers({'Content-Type'             : 'application/json',
                                       'x-sgraph-vault-write-key' : write_key})
        payload = json.dumps({'operations': operations}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def batch_read(self, vault_id: str, file_ids: list, failures: dict = None) -> dict:
        """Batch read multiple files in one request.

        Returns dict mapping file_id → bytes (payload) or None (not found).
        Automatically chunks at MAX_BATCH_OPS per request; when there is more
        than one chunk the chunks are fetched in parallel (bounded by
        BATCH_READ_WORKERS), each chunk keeping its own 502 fallback below.
        Clone's tree walk and pull's object fetch both hand this thousands of
        ids at a time; fetching the chunks one after another made a 2,000-tree
        level a multi-minute wait.

        On HTTP 502 (Lambda response-size or timeout limit): splits the failing
        chunk into single-file requests, then falls back to presigned S3 read
        for any file that still 502s.  This handles files that are too large for
        Lambda to return but small enough that they weren't flagged 'large' at
        push time.

        If ``failures`` is supplied, per-file failures are recorded into it
        as ``failures[file_id] = Schema__Fetch_Failure(...)`` — distinguishing
        objects truly absent on the server (404 / server 'not_found') from
        transient errors (5xx / network). When ``failures`` is None the
        caller opts out of classification (legacy behaviour preserved).
        """
        payloads = {}
        if not file_ids:
            return payloads                                  # nothing to ask: no request
        chunks   = [file_ids[i:i + MAX_BATCH_OPS]
                    for i in range(0, len(file_ids), MAX_BATCH_OPS)]
        if len(chunks) <= 1:
            self._batch_read_chunk_with_fallback(vault_id, chunks[0], payloads, failures)
            return payloads

        from concurrent.futures import ThreadPoolExecutor
        workers = min(BATCH_READ_WORKERS, len(chunks))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._batch_read_chunk_with_fallback,
                                       vault_id, chunk, payloads, failures)
                       for chunk in chunks]
            for future in futures:
                future.result()                 # re-raises the first chunk failure, as the serial loop did
        return payloads

    def _batch_read_chunk_with_fallback(self, vault_id: str, chunk: list, payloads: dict,
                                        failures: dict = None) -> None:
        """One chunk, with the per-file 502/503 fallback (single reads, then presigned S3)."""
        try:
            self._batch_read_chunk(vault_id, chunk, payloads, failures)
        except RuntimeError as e:
            if 'HTTP 502' not in str(e) and 'HTTP 503' not in str(e):
                raise
            # Lambda limit hit — retry each file individually, then try S3
            import sys
            print(f'  [batch_read] Lambda error for chunk of {len(chunk)} file(s) — retrying individually',
                  file=sys.stderr)
            for fid in chunk:
                try:
                    self._batch_read_chunk(vault_id, [fid], payloads, failures)
                except RuntimeError as e2:
                    if 'HTTP 502' not in str(e2) and 'HTTP 503' not in str(e2):
                        raise
                    self._presigned_read_fallback(vault_id, fid, payloads, failures)

    def _batch_read_chunk(self, vault_id: str, chunk: list, payloads: dict,
                          failures: dict = None) -> None:
        operations = [{'op': 'read', 'file_id': fid} for fid in chunk]
        url        = f'{self.base_url}/api/vault/batch/{vault_id}'
        headers    = self._auth_headers({'Content-Type': 'application/json'})
        payload    = json.dumps({'operations': operations}).encode('utf-8')
        result     = self._request('POST', url, headers, payload, idempotent=True)
        requested  = set(chunk)
        for r in result.get('results', []):
            fid    = r.get('file_id', '')
            if fid not in requested:            # a host may only answer what was asked (the id names the on-disk path)
                continue
            status = r.get('status')
            if status == 'ok' and r.get('data'):
                payloads[fid] = base64.b64decode(r['data'])
            else:
                payloads[fid] = None
                if failures is not None and fid:
                    failures[fid] = self._classify_per_file_status(fid, status, r)

    def _classify_per_file_status(self, file_id: str, status, raw_result: dict):
        """Build a Schema__Fetch_Failure for a single non-ok per-file batch result.

        The server emits ``status='not_found'`` for absent objects (see
        Vault__API__In_Memory for the canonical shape). Anything else is treated
        as transient — the verbatim status/message string is preserved.
        """
        from sgit_ai.schemas.Schema__Fetch_Failure       import Schema__Fetch_Failure
        from sgit_ai.safe_types.Enum__Fetch_Failure_Class import Enum__Fetch_Failure_Class
        from sgit_ai.safe_types.Safe_Str__Error_Message  import Safe_Str__Error_Message
        from sgit_ai.safe_types.Safe_Str__Object_Id      import Safe_Str__Object_Id

        oid          = file_id.replace('bare/data/', '')
        status_str   = str(status) if status is not None else 'unknown'
        message_text = str(raw_result.get('message', '') or raw_result.get('error', '') or status_str)
        if status_str in ('not_found', '404'):
            cls = Enum__Fetch_Failure_Class.ABSENT
        elif status_str in ('forbidden', '403'):
            cls = Enum__Fetch_Failure_Class.FORBIDDEN
        else:
            cls = Enum__Fetch_Failure_Class.TRANSIENT
        try:
            oid_safe = Safe_Str__Object_Id(oid)
        except Exception:
            oid_safe = None
        return Schema__Fetch_Failure(
            file_id        = oid_safe,
            classification = cls,
            error_message  = Safe_Str__Error_Message(message_text),
        )

    def _presigned_read_fallback(self, vault_id: str, fid: str, payloads: dict,
                                 failures: dict = None) -> None:
        """Download a single file via presigned S3 URL (fallback when Lambda 502s).

        This is the same path used by Phase 7 (large blobs) in clone.  We end
        up here when a file is too large for Lambda to serve but was not flagged
        'large=True' at push time (older CLI or threshold mismatch).
        """
        import sys
        from urllib.request import urlopen as _urlopen
        print(f'  [batch_read] Lambda 502 on {fid} — falling back to presigned S3', file=sys.stderr)
        try:
            url_info = self.presigned_read_url(vault_id, fid)
            s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
            if not s3_url:
                raise RuntimeError('no presigned URL returned')
            entry = self.debug_log.log_request('GET', s3_url) if self.debug_log else None
            with _urlopen(s3_url, context=self._ssl_context(s3_url)) as resp:
                data = resp.read()
                if entry:
                    self.debug_log.log_response(entry, resp.status, len(data))
            payloads[fid] = data
            print(f'  [batch_read] S3 fallback OK: {fid} ({len(data):,} bytes)', file=sys.stderr)
        except Exception as s3_err:
            print(f'  [batch_read] S3 fallback FAILED for {fid}: {s3_err}', file=sys.stderr)
            payloads[fid] = None
            if failures is not None and fid:
                failures[fid] = self._classify_exception(fid, s3_err)

    def _classify_exception(self, file_id: str, error: Exception):
        """Classify an exception raised while fetching a single file.

        HTTP 404 / 'Not found'  → ABSENT.
        HTTP 403 / 'Forbidden'  → FORBIDDEN.
        Everything else (5xx, network, timeouts, presigned-fallback failures)
        → TRANSIENT, preserving the underlying error string verbatim.
        """
        from sgit_ai.schemas.Schema__Fetch_Failure       import Schema__Fetch_Failure
        from sgit_ai.safe_types.Enum__Fetch_Failure_Class import Enum__Fetch_Failure_Class
        from sgit_ai.safe_types.Safe_Str__Error_Message  import Safe_Str__Error_Message
        from sgit_ai.safe_types.Safe_Str__Object_Id      import Safe_Str__Object_Id

        oid          = file_id.replace('bare/data/', '')
        error_str    = str(error)
        code         = getattr(error, 'code', None) if isinstance(error, HTTPError) else None
        is_absent    = code == 404 or 'HTTP 404' in error_str or 'Not found' in error_str
        is_forbidden = code == 403 or 'HTTP 403' in error_str or 'Forbidden' in error_str
        if is_absent:
            cls = Enum__Fetch_Failure_Class.ABSENT
        elif is_forbidden:
            cls = Enum__Fetch_Failure_Class.FORBIDDEN
        else:
            cls = Enum__Fetch_Failure_Class.TRANSIENT
        try:
            oid_safe = Safe_Str__Object_Id(oid)
        except Exception:
            oid_safe = None
        return Schema__Fetch_Failure(
            file_id        = oid_safe,
            classification = cls,
            error_message  = Safe_Str__Error_Message(error_str),
        )


    def presigned_initiate(self, vault_id: str, file_id: str,
                           file_size_bytes: int, num_parts: int,
                           write_key: str) -> dict:
        """POST /api/vault/presigned/initiate/{vault_id}
        Returns { upload_id, part_urls: [{part_number, upload_url}], part_size }.
        num_parts=0 lets the server auto-calculate (10 MB per part).
        """
        url     = f'{self.base_url}/api/vault/presigned/initiate/{vault_id}'
        headers = self._auth_headers({'Content-Type'             : 'application/json',
                                       'x-sgraph-vault-write-key' : write_key})
        payload = json.dumps({'file_id': file_id, 'file_size_bytes': file_size_bytes,
                               'num_parts': num_parts}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def presigned_complete(self, vault_id: str, file_id: str,
                           upload_id: str, parts: list,
                           write_key: str) -> dict:
        """POST /api/vault/presigned/complete/{vault_id}
        parts = [{ part_number: int, etag: str }]
        """
        url     = f'{self.base_url}/api/vault/presigned/complete/{vault_id}'
        headers = self._auth_headers({'Content-Type'             : 'application/json',
                                       'x-sgraph-vault-write-key' : write_key})
        payload = json.dumps({'file_id': file_id, 'upload_id': upload_id,
                               'parts': parts}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def presigned_cancel(self, vault_id: str, upload_id: str,
                         file_id: str, write_key: str) -> dict:
        """POST /api/vault/presigned/cancel/{vault_id}
        Best-effort cleanup of orphaned S3 parts after a failed upload.
        """
        url     = f'{self.base_url}/api/vault/presigned/cancel/{vault_id}'
        headers = self._auth_headers({'Content-Type'             : 'application/json',
                                       'x-sgraph-vault-write-key' : write_key})
        payload = json.dumps({'upload_id': upload_id, 'file_id': file_id}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
        """GET /api/vault/presigned/read-url/{vault_id}/{file_id}
        Returns { url: str, expires_in: int }. Auth is required at the gateway
        (FastAPI middleware) even though the returned S3 URL is itself signed.
        """
        url = f'{self.base_url}/api/vault/presigned/read-url/{vault_id}/{quote(file_id, safe="")}'
        return self._request('GET', url, self._auth_headers())

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        """List file IDs in a vault, optionally filtered by prefix.

        Returns a list of file_id strings.
        """
        url = f'{self.base_url}/api/vault/list/{vault_id}'
        if prefix:
            url = f'{url}?prefix={prefix}'
        result = self._request('GET', url, self._auth_headers())
        if isinstance(result, dict):
            return result.get('files', [])
        return result

    def delete_vault(self, vault_id: str, write_key: str) -> dict:
        url     = f'{self.base_url}/api/vault/destroy/{vault_id}'
        body    = json.dumps({'vault_id': vault_id}).encode('utf-8')
        headers = self._auth_headers({'Content-Type'             : 'application/json',
                                       'x-sgraph-vault-write-key' : write_key})
        return self._request('DELETE', url, headers, body)

    def tombstone_vault(self, vault_id: str, write_key: str) -> dict:
        return self.delete_vault(vault_id, write_key)

    def _ssl_context(self, url: str):
        """SSL context for the one-off urlopen calls that remain (presigned S3
        fallback) — unverified if tls_verify is False and the URL is HTTPS.
        Returns None otherwise (urllib uses the default verifier). API calls
        themselves go through the keep-alive pool, which builds its own."""
        if self.tls_verify:
            return None
        if not str(url).lower().startswith('https://'):
            return None
        return ssl._create_unverified_context()

    def _pool(self):
        if self.http_pool is None:
            with _POOL_INIT_LOCK:                      # a multi-chunk batch_read may be the first call
                if self.http_pool is None:
                    from sgit_ai.network.api.Vault__HTTP_Pool import Vault__HTTP_Pool
                    self.http_pool = Vault__HTTP_Pool(tls_verify=bool(self.tls_verify)).setup()
        return self.http_pool

    def close(self) -> None:
        """Drop every kept-alive connection. Optional — the CLI process ends anyway."""
        if self.http_pool is not None:
            self.http_pool.close()

    def _request(self, method: str, url: str, headers: dict = None, data: bytes = None,
                 idempotent: bool = None) -> dict:
        body = self._request_bytes(method, url, headers, data, idempotent=idempotent)
        if body:
            return json.loads(body)
        return {}

    def _request_bytes(self, method: str, url: str, headers: dict = None, data: bytes = None,
                       idempotent: bool = None) -> bytes:
        """One API call with the transient-status retry loop (502/503/504, backing
        off per RETRY_DELAYS) over a kept-alive connection. Raises the same
        RuntimeError shapes as before (`API Error: HTTP <code> ...`) so every
        caller that classifies by status text keeps working; a connection-level
        failure surfaces as urllib's URLError, as urlopen raised it."""
        if idempotent is None:
            idempotent = method.upper() == 'GET'
        data_size  = len(data) if data else 0
        last_error = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            entry = self.debug_log.log_request(method, url, data_size) if self.debug_log else None
            try:
                status, body = self._send(method, url, headers, data, idempotent)
                if entry:
                    self.debug_log.log_response(entry, status, len(body))
                return body
            except HTTPError as e:
                if entry:
                    self.debug_log.log_error(entry, e.code, e.reason)
                if e.code in TRANSIENT_STATUS_CODES and attempt < len(RETRY_DELAYS):
                    last_error = e
                    continue
                raise self._api_error(method, url, headers, e, data_size=data_size)
        raise self._api_error(method, url, headers, last_error, data_size=data_size)

    def _send(self, method: str, url: str, headers: dict, data: bytes, idempotent: bool,
              retried: bool = False) -> tuple:
        """(status, body) for one HTTP exchange on a pooled connection.

        * >= 300 raises HTTPError (3xx included: redirects are NOT followed, so
          the token headers can never be replayed to another host — urlopen
          copied every header onto the redirected request).
        * A failure between sending and reading the whole body discards the
          connection. If the connection was WARM (had served a request — the
          stale-keep-alive case) and the request is idempotent, it is resent
          once on a FRESH connection (never another idle one); a write is
          never resent, because the server may already have applied it. The
          pool's liveness and idle-age checks make this the race window only.
        """
        pool            = self._pool()
        key, conn, warm = pool.acquire(url, fresh=retried)
        target          = pool.request_target(key, url)
        send_headers    = {'User-Agent': 'sgit-ai'}      # the network layer may not import _version (layer rule)
        send_headers.update(pool.proxy_headers(key))
        send_headers.update(headers or {})
        try:
            conn.request(method, target, body=data, headers=send_headers)
            response = conn.getresponse()
            status   = response.status
            reason   = response.reason
            body     = response.read()
            closing  = response.will_close or (response.getheader('Connection', '') or '').lower() == 'close'
        except (http.client.HTTPException, OSError) as error:
            pool.discard(key, conn)
            if warm and idempotent and not retried:
                return self._send(method, url, headers, data, idempotent, retried=True)
            raise URLError(error) from error
        if closing or os.environ.get('SGIT_HTTP_NO_KEEPALIVE'):   # env: A/B switch — one connection per request, as before
            pool.discard(key, conn)
        else:
            pool.release(key, conn)
        if status >= 300:
            raise HTTPError(url, status, reason, response.headers, io.BytesIO(body))
        return status, body

    def _api_error(self, method: str, url: str, headers: dict, error: HTTPError, data_size: int = 0) -> Exception:
        response_body = ''
        try:
            response_body = error.read().decode('utf-8', errors='replace')
        except Exception:
            pass

        masked_headers = {}
        for k, v in (headers or {}).items():
            if 'token' in k.lower() or 'key' in k.lower():
                masked_headers[k] = f'***...({len(v)} chars)'
            else:
                masked_headers[k] = v

        lines = [f'API Error: HTTP {error.code} {error.reason}',
                 f'  Request:  {method} {url}',
                 f'  Headers:  {json.dumps(masked_headers, indent=2)}']
        if data_size:
            lines.append(f'  Payload:  {data_size} bytes')
        if response_body:
            lines.append(f'  Response: {response_body}')

        # Hint: if the FastAPI gate rejects with "Client API key is missing" and
        # we're not sending X-API-Key, the user is on an older sgit against a
        # new-style v0.2.6+ vault-app stack. This client always sends X-API-Key,
        # so seeing this body usually means the token value itself is wrong.
        if 300 <= error.code < 400:
            location = ''
            try:
                location = error.headers.get('Location', '') if error.headers else ''
            except Exception:
                pass
            lines.append(f'  Hint:     the server redirected{(" to " + location) if location else ""}. '
                         'sgit does not follow redirects (so its credentials are never sent to '
                         'another host): set --base-url (or the remote) to the final https URL.')
        if error.code == 401 and 'Client API key is missing' in response_body:
            lines.append('  Hint:     the vault-app gate rejected the API key — check your access token '
                         '(sgit auth) and that --token matches the value from `sp vault-app info`.')

        message = '\n'.join(lines)
        return RuntimeError(message)
