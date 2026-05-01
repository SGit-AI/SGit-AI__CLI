import base64
import json
import time
from   urllib.parse                                  import quote
from   urllib.request                                import Request, urlopen
from   urllib.error                                  import HTTPError
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.safe_types.Safe_Str__Base_URL     import Safe_Str__Base_URL
from   sgit_ai.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token

TRANSIENT_STATUS_CODES = {502, 503, 504}
RETRY_DELAYS           = [2, 4, 8]            # seconds between attempts

DEFAULT_BASE_URL       = 'https://dev.send.sgraph.ai'
LARGE_BLOB_THRESHOLD   = 4 * 1024 * 1024   # 4 MB — safe margin under Lambda base64 limit (~4.7 MB)
MAX_BATCH_OPS          = 50                 # conservative margin under server's 100-op hard limit


class Vault__API(Type_Safe):
    base_url     : Safe_Str__Base_URL     = None
    access_token : Safe_Str__Access_Token = None
    debug_log    : object                 = None

    def setup(self):
        if not self.base_url:
            self.base_url = DEFAULT_BASE_URL
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        url     = f'{self.base_url}/api/vault/write/{vault_id}/{quote(file_id, safe="")}'
        headers = {'Content-Type'              : 'application/octet-stream',
                    'x-sgraph-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
        return self._request('PUT', url, headers, payload)

    def read(self, vault_id: str, file_id: str) -> bytes:
        url = f'{self.base_url}/api/vault/read/{vault_id}/{quote(file_id, safe="")}'
        return self._request_bytes('GET', url)

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        url     = f'{self.base_url}/api/vault/delete/{vault_id}/{quote(file_id, safe="")}'
        headers = {'x-sgraph-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
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
        headers = {'Content-Type'             : 'application/json',
                   'x-sgraph-access-token'    : self.access_token,
                   'x-sgraph-vault-write-key' : write_key}
        payload = json.dumps({'operations': operations}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def batch_read(self, vault_id: str, file_ids: list) -> dict:
        """Batch read multiple files in one request.

        Returns dict mapping file_id → bytes (payload) or None (not found).
        Automatically chunks at MAX_BATCH_OPS per request.

        On HTTP 502 (Lambda response-size or timeout limit): splits the failing
        chunk into single-file requests, then falls back to presigned S3 read
        for any file that still 502s.  This handles files that are too large for
        Lambda to return but small enough that they weren't flagged 'large' at
        push time.
        """
        payloads = {}
        for i in range(0, max(len(file_ids), 1), MAX_BATCH_OPS):
            chunk = file_ids[i:i + MAX_BATCH_OPS]
            try:
                self._batch_read_chunk(vault_id, chunk, payloads)
            except RuntimeError as e:
                if 'HTTP 502' not in str(e) and 'HTTP 503' not in str(e):
                    raise
                # Lambda limit hit — retry each file individually, then try S3
                import sys
                print(f'  [batch_read] Lambda error for chunk of {len(chunk)} file(s) — retrying individually',
                      file=sys.stderr)
                for fid in chunk:
                    try:
                        self._batch_read_chunk(vault_id, [fid], payloads)
                    except RuntimeError as e2:
                        if 'HTTP 502' not in str(e2) and 'HTTP 503' not in str(e2):
                            raise
                        self._presigned_read_fallback(vault_id, fid, payloads)
        return payloads

    def _batch_read_chunk(self, vault_id: str, chunk: list, payloads: dict) -> None:
        operations = [{'op': 'read', 'file_id': fid} for fid in chunk]
        url        = f'{self.base_url}/api/vault/batch/{vault_id}'
        headers    = {'Content-Type': 'application/json'}
        payload    = json.dumps({'operations': operations}).encode('utf-8')
        result     = self._request('POST', url, headers, payload)
        for r in result.get('results', []):
            fid = r.get('file_id', '')
            if r.get('status') == 'ok' and r.get('data'):
                payloads[fid] = base64.b64decode(r['data'])
            else:
                payloads[fid] = None

    def _presigned_read_fallback(self, vault_id: str, fid: str, payloads: dict) -> None:
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
            with _urlopen(s3_url) as resp:
                data = resp.read()
                if entry:
                    self.debug_log.log_response(entry, resp.status, len(data))
            payloads[fid] = data
            print(f'  [batch_read] S3 fallback OK: {fid} ({len(data):,} bytes)', file=sys.stderr)
        except Exception as s3_err:
            print(f'  [batch_read] S3 fallback FAILED for {fid}: {s3_err}', file=sys.stderr)
            payloads[fid] = None


    def presigned_initiate(self, vault_id: str, file_id: str,
                           file_size_bytes: int, num_parts: int,
                           write_key: str) -> dict:
        """POST /api/vault/presigned/initiate/{vault_id}
        Returns { upload_id, part_urls: [{part_number, upload_url}], part_size }.
        num_parts=0 lets the server auto-calculate (10 MB per part).
        """
        url     = f'{self.base_url}/api/vault/presigned/initiate/{vault_id}'
        headers = {'Content-Type'             : 'application/json',
                   'x-sgraph-access-token'    : self.access_token,
                   'x-sgraph-vault-write-key' : write_key}
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
        headers = {'Content-Type'             : 'application/json',
                   'x-sgraph-access-token'    : self.access_token,
                   'x-sgraph-vault-write-key' : write_key}
        payload = json.dumps({'file_id': file_id, 'upload_id': upload_id,
                               'parts': parts}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def presigned_cancel(self, vault_id: str, upload_id: str,
                         file_id: str, write_key: str) -> dict:
        """POST /api/vault/presigned/cancel/{vault_id}
        Best-effort cleanup of orphaned S3 parts after a failed upload.
        """
        url     = f'{self.base_url}/api/vault/presigned/cancel/{vault_id}'
        headers = {'Content-Type'             : 'application/json',
                   'x-sgraph-access-token'    : self.access_token,
                   'x-sgraph-vault-write-key' : write_key}
        payload = json.dumps({'upload_id': upload_id, 'file_id': file_id}).encode('utf-8')
        return self._request('POST', url, headers, payload)

    def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
        """GET /api/vault/presigned/read-url/{vault_id}/{file_id}
        Returns { url: str, expires_in: int }. No auth required (data is encrypted).
        Client then does a raw urllib GET on the URL to fetch encrypted blob from S3.
        """
        url = f'{self.base_url}/api/vault/presigned/read-url/{vault_id}/{quote(file_id, safe="")}'
        return self._request('GET', url)

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        """List file IDs in a vault, optionally filtered by prefix.

        Returns a list of file_id strings.
        """
        url = f'{self.base_url}/api/vault/list/{vault_id}'
        if prefix:
            url = f'{url}?prefix={prefix}'
        result = self._request('GET', url)
        if isinstance(result, dict):
            return result.get('files', [])
        return result

    def delete_vault(self, vault_id: str, write_key: str) -> dict:
        """Hard-delete every server-side file belonging to vault_id.

        Returns {'status': 'deleted', 'vault_id': ..., 'files_deleted': N}.
        files_deleted == 0 means the vault was already gone — not an error.
        Raises RuntimeError on 403 (bad write key) or 409 (vault_id mismatch).
        """
        url     = f'{self.base_url}/api/vault/destroy/{vault_id}'
        body    = json.dumps({'vault_id': vault_id}).encode('utf-8')
        headers = {'Content-Type'             : 'application/json',
                   'x-sgraph-vault-write-key' : write_key}
        return self._request('DELETE', url, headers, body)

    def _request(self, method: str, url: str, headers: dict = None, data: bytes = None) -> dict:
        last_error = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            req = Request(url, data=data, method=method)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)
            entry = self.debug_log.log_request(method, url, len(data) if data else 0) if self.debug_log else None
            try:
                with urlopen(req) as response:
                    body = response.read()
                    if entry:
                        self.debug_log.log_response(entry, response.status, len(body))
                    if body:
                        return json.loads(body)
                    return {}
            except HTTPError as e:
                if entry:
                    self.debug_log.log_error(entry, e.code, e.reason)
                if e.code in TRANSIENT_STATUS_CODES and attempt < len(RETRY_DELAYS):
                    last_error = e
                    continue
                raise self._api_error(method, url, headers, e, data_size=len(data) if data else 0)
        raise self._api_error(method, url, headers, last_error, data_size=len(data) if data else 0)

    def _request_bytes(self, method: str, url: str, headers: dict = None) -> bytes:
        last_error = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            req = Request(url, method=method)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)
            entry = self.debug_log.log_request(method, url) if self.debug_log else None
            try:
                with urlopen(req) as response:
                    body = response.read()
                    if entry:
                        self.debug_log.log_response(entry, response.status, len(body))
                    return body
            except HTTPError as e:
                if entry:
                    self.debug_log.log_error(entry, e.code, e.reason)
                if e.code in TRANSIENT_STATUS_CODES and attempt < len(RETRY_DELAYS):
                    last_error = e
                    continue
                raise self._api_error(method, url, headers, e)
        raise self._api_error(method, url, headers, last_error)

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

        message = '\n'.join(lines)
        return RuntimeError(message)
