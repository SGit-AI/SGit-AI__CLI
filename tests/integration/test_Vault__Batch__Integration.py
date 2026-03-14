"""Integration tests for batch API and change packs against the local SG/Send server.

Validates that:
- POST /api/vault/batch/{vault_id} works end-to-end
- GET /api/vault/list/{vault_id} works end-to-end
- Push uses batch API correctly against a real server
- Change packs can be created and drained
- GC drain integrates blobs into the object store
"""
import base64
import json
import os

import pytest

from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.sync.Vault__Storage         import Vault__Storage
from sg_send_cli.sync.Vault__Change_Pack     import Vault__Change_Pack
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store


class Test_Vault__Batch__Integration__API:
    """Test the batch and list API endpoints against the real server."""

    def test_batch_write_single_file(self, vault_api, crypto):
        keys      = crypto.derive_keys('batchtest', 'batchvid')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        plaintext  = b'batch write test'
        ciphertext = crypto.encrypt(read_key, plaintext)

        operations = [dict(op='write',
                           file_id='batch-file-01',
                           data=base64.b64encode(ciphertext).decode())]

        result = vault_api.batch('batchvid', write_key, operations)
        assert 'results' in result
        assert result['results'][0]['status'] == 'ok'

        downloaded = vault_api.read('batchvid', 'batch-file-01')
        decrypted  = crypto.decrypt(read_key, downloaded)
        assert decrypted == plaintext

    def test_batch_write_multiple_files(self, vault_api, crypto):
        keys      = crypto.derive_keys('batchmulti', 'batchmul')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        operations = []
        for i in range(3):
            ciphertext = crypto.encrypt(read_key, f'file {i}'.encode())
            operations.append(dict(op='write',
                                   file_id=f'multi-file-{i:02d}',
                                   data=base64.b64encode(ciphertext).decode()))

        result = vault_api.batch('batchmul', write_key, operations)
        assert 'results' in result
        assert len(result['results']) == 3

        for i in range(3):
            downloaded = vault_api.read('batchmul', f'multi-file-{i:02d}')
            decrypted  = crypto.decrypt(read_key, downloaded)
            assert decrypted == f'file {i}'.encode()

    def test_batch_write_then_delete(self, vault_api, crypto):
        keys      = crypto.derive_keys('batchdel', 'batchdel')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        ciphertext = crypto.encrypt(read_key, b'delete me via batch')
        vault_api.batch('batchdel', write_key,
                        [dict(op='write', file_id='to-delete',
                              data=base64.b64encode(ciphertext).decode())])

        vault_api.read('batchdel', 'to-delete')

        vault_api.batch('batchdel', write_key,
                        [dict(op='delete', file_id='to-delete')])

        with pytest.raises(RuntimeError, match='404'):
            vault_api.read('batchdel', 'to-delete')

    def test_list_files_empty_vault(self, vault_api):
        try:
            result = vault_api.list_files('empty-list-vault')
            if isinstance(result, list):
                assert result == []
            else:
                assert result.get('files', []) == []
        except RuntimeError:
            pass

    def test_list_files_after_writes(self, vault_api, crypto):
        keys      = crypto.derive_keys('listtest', 'listvid1')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        for i in range(3):
            ciphertext = crypto.encrypt(read_key, f'list file {i}'.encode())
            vault_api.write('listvid1', f'list-file-{i:02d}', write_key, ciphertext)

        result = vault_api.list_files('listvid1')
        if isinstance(result, list):
            files = result
        else:
            files = result.get('files', [])
        assert len(files) >= 3


class Test_Vault__Batch__Integration__Push:
    """Test that push() works against the real server using batch API."""

    def test_push_uses_batch_against_real_server(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'batch-push-vault')
        sync.init(vault_dir, vault_key='batchpush:batchpsh')

        with open(os.path.join(vault_dir, 'test.txt'), 'w') as f:
            f.write('batch push test')
        sync.commit(vault_dir, message='add test file')

        result = sync.push(vault_dir)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] >= 1

    def test_push_delta_only_against_real_server(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'batch-delta-vault')
        sync.init(vault_dir, vault_key='batchdelta:batchdlt')

        with open(os.path.join(vault_dir, 'first.txt'), 'w') as f:
            f.write('first file')
        sync.commit(vault_dir, message='first')
        sync.push(vault_dir)

        with open(os.path.join(vault_dir, 'second.txt'), 'w') as f:
            f.write('second file')
        sync.commit(vault_dir, message='second')
        result = sync.push(vault_dir)

        assert result['status']          == 'pushed'
        assert result['objects_uploaded'] == 1

    def test_push_fallback_when_batch_unavailable(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'fallback-vault')
        sync.init(vault_dir, vault_key='fallback:fallbck1')

        with open(os.path.join(vault_dir, 'file.txt'), 'w') as f:
            f.write('fallback test')
        sync.commit(vault_dir, message='add file')

        result = sync.push(vault_dir, use_batch=False)
        assert result['status'] == 'pushed'


class Test_Vault__Batch__Integration__Change_Pack:
    """Test change pack creation and GC drain against the real server."""

    def test_create_change_pack_and_drain(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'gc-vault')
        sync.init(vault_dir, vault_key='gctest:gctestvd')

        pack_result = sync.create_change_pack(vault_dir, files={
            'external.txt': 'data from external source'
        })
        assert pack_result['pack_id'].startswith('pack-')

        storage     = Vault__Storage()
        change_pack = Vault__Change_Pack(crypto=crypto, storage=storage)
        packs       = change_pack.list_pending_packs(vault_dir)
        assert len(packs) == 1

        gc_result = sync.gc_drain(vault_dir)
        assert gc_result['drained'] == 1

        packs_after = change_pack.list_pending_packs(vault_dir)
        assert len(packs_after) == 0

    def test_gc_drain_copies_blobs_to_object_store(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'gc-blob-vault')
        sync.init(vault_dir, vault_key='gcblob:gcblobvd')

        pack_result = sync.create_change_pack(vault_dir, files={
            'data.bin': b'\x00\x01\x02\x03'
        })
        blob_id = pack_result['file_ids'][0]

        sync.gc_drain(vault_dir)

        sg_dir    = os.path.join(vault_dir, '.sg_vault')
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto, use_v2=True)
        assert obj_store.exists(blob_id)
