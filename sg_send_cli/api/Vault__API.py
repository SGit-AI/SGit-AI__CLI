import base64
import json
from   urllib.request                                import Request, urlopen
from   urllib.error                                  import HTTPError
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.safe_types.Safe_Str__Base_URL     import Safe_Str__Base_URL
from   sg_send_cli.safe_types.Safe_Str__Access_Token import Safe_Str__Access_Token

DEFAULT_BASE_URL = 'https://send.sgraph.ai'


class Vault__API(Type_Safe):
    base_url     : Safe_Str__Base_URL     = None
    access_token : Safe_Str__Access_Token = None

    def setup(self):
        if not self.base_url:
            self.base_url = DEFAULT_BASE_URL
        return self

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        url     = f'{self.base_url}/api/vault/write/{vault_id}/{file_id}'
        headers = {'Content-Type'              : 'application/octet-stream',
                    'x-sgraph-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
        return self._request('PUT', url, headers, payload)

    def read(self, vault_id: str, file_id: str) -> bytes:
        url = f'{self.base_url}/api/vault/read/{vault_id}/{file_id}'
        return self._request_bytes('GET', url)

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        url     = f'{self.base_url}/api/vault/delete/{vault_id}/{file_id}'
        headers = {'x-sgraph-access-token': self.access_token,
                    'x-sgraph-vault-write-key'  : write_key}
        return self._request('DELETE', url, headers)

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Execute a batch of operations atomically.

        Each operation is a dict with:
            op      : 'write' | 'write-if-match' | 'delete'
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
