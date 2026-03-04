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
        with urlopen(req) as response:
            body = response.read()
            if body:
                return json.loads(body)
            return {}

    def _request_bytes(self, method: str, url: str, headers: dict = None) -> bytes:
        req = Request(url, method=method)
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        with urlopen(req) as response:
            return response.read()
