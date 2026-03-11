import json
from   urllib.request                                import Request, urlopen
from   urllib.error                                  import HTTPError
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.safe_types.Safe_Str__Base_URL     import Safe_Str__Base_URL
from   sg_send_cli.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token

DEFAULT_BASE_URL      = 'https://send.sgraph.ai'
LAMBDA_RESPONSE_LIMIT = 5 * 1024 * 1024                                   # 5MB


class API__Transfer(Type_Safe):
    base_url     : Safe_Str__Base_URL     = None
    access_token : Safe_Str__Access_Token = None

    def setup(self):
        if not self.base_url:
            self.base_url = DEFAULT_BASE_URL
        return self

    # --- Transfer lifecycle ---

    def create(self, file_size_bytes: int, content_type_hint: str = 'application/octet-stream') -> dict:
        url  = f'{self.base_url}/api/transfers/create'
        body = json.dumps(dict(file_size_bytes=file_size_bytes, content_type_hint=content_type_hint)).encode()
        return self._request_json('POST', url, self._auth_headers({'Content-Type': 'application/json'}), body)

    def upload(self, transfer_id: str, encrypted_payload: bytes) -> dict:
        url     = f'{self.base_url}/api/transfers/upload/{transfer_id}'
        headers = self._auth_headers({'Content-Type': 'application/octet-stream'})
        return self._request_json('POST', url, headers, encrypted_payload)

    def complete(self, transfer_id: str) -> dict:
        url = f'{self.base_url}/api/transfers/complete/{transfer_id}'
        return self._request_json('POST', url, self._auth_headers())

    def info(self, transfer_id: str) -> dict:
        url = f'{self.base_url}/api/transfers/info/{transfer_id}'
        return self._request_json('GET', url)

    def download(self, transfer_id: str) -> bytes:
        url = f'{self.base_url}/api/transfers/download/{transfer_id}'
        return self._request_bytes('GET', url)

    def download_base64(self, transfer_id: str) -> dict:
        url = f'{self.base_url}/api/transfers/download-base64/{transfer_id}'
        return self._request_json('GET', url)

    # --- Token management ---

    def check_token(self, token_name: str) -> dict:
        url = f'{self.base_url}/api/transfers/check-token/{token_name}'
        return self._request_json('GET', url)

    # --- Presigned (large file) operations ---

    def presigned_capabilities(self) -> dict:
        url = f'{self.base_url}/api/presigned/capabilities'
        return self._request_json('GET', url)

    def presigned_initiate(self, transfer_id: str, file_size_bytes: int, num_parts: int) -> dict:
        url  = f'{self.base_url}/api/presigned/initiate'
        body = json.dumps(dict(transfer_id=transfer_id, file_size_bytes=file_size_bytes, num_parts=num_parts)).encode()
        return self._request_json('POST', url, self._auth_headers({'Content-Type': 'application/json'}), body)

    def presigned_complete(self, transfer_id: str, upload_id: str, parts: list) -> dict:
        url  = f'{self.base_url}/api/presigned/complete'
        body = json.dumps(dict(transfer_id=transfer_id, upload_id=upload_id, parts=parts)).encode()
        return self._request_json('POST', url, self._auth_headers({'Content-Type': 'application/json'}), body)

    def presigned_abort(self, transfer_id: str, upload_id: str) -> dict:
        url = f'{self.base_url}/api/presigned/abort/{transfer_id}/{upload_id}'
        return self._request_json('POST', url, self._auth_headers())

    def presigned_upload_url(self, transfer_id: str) -> dict:
        url = f'{self.base_url}/api/presigned/upload-url/{transfer_id}'
        return self._request_json('GET', url, self._auth_headers())

    def presigned_download_url(self, transfer_id: str) -> dict:
        url = f'{self.base_url}/api/presigned/download-url/{transfer_id}'
        return self._request_json('GET', url)

    # --- Upload a presigned part directly to S3 ---

    def upload_part(self, upload_url: str, part_data: bytes) -> str:
        req = Request(upload_url, data=part_data, method='PUT')
        req.add_header('Content-Type', 'application/octet-stream')
        try:
            with urlopen(req) as response:
                return response.headers.get('ETag', '')
        except HTTPError as e:
            raise self._api_error('PUT', upload_url, {}, e, data_size=len(part_data))

    # --- High-level helpers ---

    def upload_file(self, encrypted_payload: bytes) -> str:
        resp        = self.create(len(encrypted_payload))
        transfer_id = resp['transfer_id']

        if len(encrypted_payload) <= LAMBDA_RESPONSE_LIMIT:
            self.upload(transfer_id, encrypted_payload)
        else:
            self._upload_large(transfer_id, encrypted_payload)

        self.complete(transfer_id)
        return transfer_id

    def download_file(self, transfer_id: str) -> bytes:
        info = self.info(transfer_id)
        size = info.get('file_size_bytes', 0)

        if size <= LAMBDA_RESPONSE_LIMIT:
            return self.download(transfer_id)
        else:
            resp = self.presigned_download_url(transfer_id)
            return self._request_bytes('GET', resp['download_url'])

    # --- Internal ---

    def _upload_large(self, transfer_id: str, payload: bytes):
        caps = self.presigned_capabilities()
        if not caps.get('presigned_available'):
            raise RuntimeError('Server does not support presigned uploads for large files')

        min_part = caps.get('min_part_size_bytes', 5 * 1024 * 1024)
        max_part = caps.get('max_part_size_bytes', 100 * 1024 * 1024)
        part_size = max(min_part, min(max_part, len(payload) // 10))
        num_parts = (len(payload) + part_size - 1) // part_size

        resp      = self.presigned_initiate(transfer_id, len(payload), num_parts)
        upload_id = resp['upload_id']
        parts     = resp['parts']

        completed_parts = []
        try:
            for part_info in parts:
                part_num  = part_info['part_number']
                start     = (part_num - 1) * part_size
                end       = min(start + part_size, len(payload))
                part_data = payload[start:end]
                etag      = self.upload_part(part_info['upload_url'], part_data)
                completed_parts.append(dict(part_number=part_num, etag=etag))

            self.presigned_complete(transfer_id, upload_id, completed_parts)
        except Exception:
            self.presigned_abort(transfer_id, upload_id)
            raise

    def _auth_headers(self, extra: dict = None) -> dict:
        headers = {}
        if self.access_token:
            headers['x-sgraph-access-token'] = str(self.access_token)
        if extra:
            headers.update(extra)
        return headers

    def _request_json(self, method: str, url: str, headers: dict = None, data: bytes = None) -> dict:
        req = Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, str(value))
        try:
            with urlopen(req) as response:
                body = response.read()
                if body:
                    return json.loads(body)
                return {}
        except HTTPError as e:
            raise self._api_error(method, url, headers, e, data_size=len(data) if data else 0)

    def _request_bytes(self, method: str, url: str, headers: dict = None) -> bytes:
        req = Request(url, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, str(value))
        try:
            with urlopen(req) as response:
                return response.read()
        except HTTPError as e:
            raise self._api_error(method, url, headers, e)

    def _api_error(self, method: str, url: str, headers: dict, error: HTTPError, data_size: int = 0) -> Exception:
        response_body = ''
        try:
            response_body = error.read().decode('utf-8', errors='replace')
        except Exception:
            pass

        masked_headers = {}
        for k, v in (headers or {}).items():
            if 'token' in k.lower() or 'key' in k.lower():
                masked_headers[k] = f'{str(v)[:8]}...({len(str(v))} chars)'
            else:
                masked_headers[k] = v

        lines = [f'API Error: HTTP {error.code} {error.reason}',
                 f'  Request:  {method} {url}',
                 f'  Headers:  {json.dumps(masked_headers, indent=2)}']
        if data_size:
            lines.append(f'  Payload:  {data_size} bytes')
        if response_body:
            lines.append(f'  Response: {response_body}')

        return RuntimeError('\n'.join(lines))
