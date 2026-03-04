import json
from   urllib.request                  import Request, urlopen
from   urllib.error                    import HTTPError
from   osbot_utils.type_safe.Type_Safe import Type_Safe

DEFAULT_BASE_URL = 'https://send.sgraph.ai'


class Vault__API(Type_Safe):
    base_url     : str
    access_token : str

    def setup(self):
        if not self.base_url:
            self.base_url = DEFAULT_BASE_URL
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        url     = f'{self.base_url}/api/vault/write/{vault_id}/{file_id}'
        headers = {'Content-Type'              : 'application/octet-stream',
                    'x-sgraph-send-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
        return self._request('PUT', url, headers, payload)

    def read(self, vault_id: str, file_id: str) -> bytes:
        url = f'{self.base_url}/api/vault/read/{vault_id}/{file_id}'
        return self._request_bytes('GET', url)

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        url     = f'{self.base_url}/api/vault/delete/{vault_id}/{file_id}'
        headers = {'x-sgraph-send-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
        return self._request('DELETE', url, headers)

    def _request(self, method: str, url: str, headers: dict = None, data: bytes = None) -> dict:
        req = Request(url, data=data, method=method)
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
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
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
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
                masked_headers[k] = f'{v[:8]}...({len(v)} chars)'
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
