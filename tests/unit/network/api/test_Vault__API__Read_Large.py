"""Large blobs against a server without S3 (memory or disk storage: `sgit serve`, a CI
sidecar, a self-hosted server): the presigned route answers 400 'S3 storage mode
required', so reads fall back to the ordinary read route and pushes to the batch."""
import pytest

from sgit_ai.core.actions.push.Vault__Batch  import Vault__Batch
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.network.api.Vault__API          import Vault__API
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

NO_S3   = ('API Error: HTTP 400 Bad Request\n  URL: https://example.test/api/vault/presigned/read-url/v/f\n'
           '  Response: {"detail":"S3 storage mode required"}')
MISSING = 'API Error: HTTP 404 Not Found\n  Response: {"detail":"Not Found"}'
DENIED  = 'API Error: HTTP 403 Forbidden\n  Response: {"detail":"Access token required"}'


class API__Without_S3(Vault__API):
    """A disk-mode server: no presigned route, a read route that serves any size."""
    def presigned_read_url(self, vault_id, file_id):
        raise RuntimeError(NO_S3)
    def read(self, vault_id, file_id):
        return b'the whole blob ' + file_id.encode()
    def presigned_initiate(self, vault_id, file_id, file_size_bytes, num_parts, write_key):
        raise RuntimeError(NO_S3.replace('read-url/v/f', 'initiate/v'))


class API__With_S3(Vault__API):
    def presigned_read_url(self, vault_id, file_id):
        return {'url': 'https://s3.example.test/signed'}
    def fetch_presigned(self, url, timeout=300):
        return b'from s3 ' + url.encode()
    def read(self, vault_id, file_id):
        raise AssertionError('the read route must not be used when the server has S3')


class API__Denying(Vault__API):
    def presigned_read_url(self, vault_id, file_id):
        raise RuntimeError(DENIED)
    def read(self, vault_id, file_id):
        raise AssertionError('a 403 is not "no S3": it must surface, not fall back')


class Test_Vault__API__Read_Large:

    def test_which_answers_mean_the_server_has_no_presigned_route(self):
        api = Vault__API()
        assert api.presigned_unavailable(RuntimeError(NO_S3))
        assert api.presigned_unavailable(RuntimeError(MISSING))
        assert api.presigned_unavailable(RuntimeError('presigned_not_available'))     # the in-memory test host
        assert not api.presigned_unavailable(RuntimeError(DENIED))
        assert not api.presigned_unavailable(RuntimeError('API Error: HTTP 502 Bad Gateway'))

    def test_without_s3_the_read_route_serves_the_blob(self):
        assert API__Without_S3().read_large('v', 'bare/data/obj-1') == b'the whole blob bare/data/obj-1'

    def test_with_s3_the_presigned_url_is_used(self):
        assert API__With_S3().read_large('v', 'bare/data/obj-1') == b'from s3 https://s3.example.test/signed'

    def test_a_denial_is_not_a_fallback(self):
        with pytest.raises(RuntimeError, match='403'):
            API__Denying().read_large('v', 'bare/data/obj-1')

    def test_in_memory_host_falls_back_too(self):
        api = Vault__API__In_Memory().setup()
        api._store['v/bare/data/obj-1'] = b'payload'
        assert api.read_large('v', 'bare/data/obj-1') == b'payload'

    def test_a_push_without_s3_carries_the_large_blob_in_the_batch(self):
        batch = Vault__Batch(crypto=Vault__Crypto(), api=API__Without_S3())
        assert batch._upload_large('v', 'bare/data/obj-1', b'x' * 10, 'write-key') is False   # caller batches it

    def test_a_push_denied_by_the_server_still_fails(self):
        class API__Initiate_Denied(API__Without_S3):
            def presigned_initiate(self, *a, **k):
                raise RuntimeError(DENIED)
        batch = Vault__Batch(crypto=Vault__Crypto(), api=API__Initiate_Denied())
        with pytest.raises(RuntimeError, match='403'):
            batch._upload_large('v', 'bare/data/obj-1', b'x' * 10, 'write-key')
