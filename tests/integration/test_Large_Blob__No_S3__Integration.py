"""Issue 2 of the 14 Oct report: a file over 4 MB could not be pushed to a server without
S3 (the memory and disk backends: `sgit serve`, a CI sidecar), and a large file could not
be fetched on demand into a sparse clone from one. The test server here runs in memory
mode, which has no presigned route either, so this is the real failure reproduced.

Requires the Python-3.12 venv with sgraph-ai-app-send:
  /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/ -v
"""
import os

from sgit_ai.core.Vault__Sync     import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
from sgit_ai.network.api.Vault__API import LARGE_BLOB_THRESHOLD

BIG = os.urandom(LARGE_BLOB_THRESHOLD + 256 * 1024)              # ~4.25 MB of incompressible bytes


class Test_Large_Blob__No_S3__Integration:

    def test_push_clone_and_sparse_fetch_of_a_large_file(self, vault_api, temp_dir):
        sync    = Vault__Sync(crypto=Vault__Crypto(), api=vault_api)
        src_dir = os.path.join(temp_dir, 'src')
        key     = 'largeblob:largebl01'
        sync.init(src_dir, vault_key=key)
        os.makedirs(os.path.join(src_dir, 'media'))
        with open(os.path.join(src_dir, 'media', 'big.bin'), 'wb') as f:
            f.write(BIG)
        with open(os.path.join(src_dir, 'small.txt'), 'w') as f:
            f.write('small')
        sync.commit(src_dir, message='a large file')
        sync.push(src_dir)                                                        # used to fail: S3 storage mode required

        clone_dir = os.path.join(temp_dir, 'clone')
        sync.clone(key, clone_dir)
        with open(os.path.join(clone_dir, 'media', 'big.bin'), 'rb') as f:
            assert f.read() == BIG

        sparse_dir = os.path.join(temp_dir, 'sparse')
        sync.clone(key, sparse_dir, sparse=True)
        assert not os.path.exists(os.path.join(sparse_dir, 'media', 'big.bin'))
        result = sync.sparse_fetch(sparse_dir, path='media/big.bin')                # used to fail the same way
        assert result['written'] == ['media/big.bin']
        with open(os.path.join(sparse_dir, 'media', 'big.bin'), 'rb') as f:
            assert f.read() == BIG
        assert sync.sparse_cat(sparse_dir, 'small.txt') == b'small'
