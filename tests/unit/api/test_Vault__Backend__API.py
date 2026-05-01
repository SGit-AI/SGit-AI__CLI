"""Tests for Vault__Backend__API — the HTTP-API-backed Vault__Backend implementation.

Uses Vault__API__In_Memory as the server so no real HTTP calls are made.
"""
import base64

import pytest

from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.api.Vault__Backend__API   import Vault__Backend__API
from sgit_ai.safe_types.Safe_Str__Vault_Id  import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Write_Key import Safe_Str__Write_Key

VALID_VAULT_ID  = 'testvault1'
VALID_WRITE_KEY = 'a' * 64   # 64 hex chars (all 'a' is valid hex)


def _make_backend(vault_id: str = VALID_VAULT_ID,
                  write_key: str = VALID_WRITE_KEY) -> Vault__Backend__API:
    api      = Vault__API__In_Memory()
    api.setup()
    backend  = Vault__Backend__API(
        api       = api,
        vault_id  = vault_id,
        write_key = write_key,
    )
    return backend


class Test_Vault__Backend__API:

    def setup_method(self):
        self.backend = _make_backend()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_backend_has_api(self):
        assert isinstance(self.backend.api, Vault__API__In_Memory)

    def test_backend_vault_id_set(self):
        assert str(self.backend.vault_id) == VALID_VAULT_ID

    def test_backend_write_key_set(self):
        assert str(self.backend.write_key) == VALID_WRITE_KEY

    # ------------------------------------------------------------------
    # write / read round-trip
    # ------------------------------------------------------------------

    def test_write_returns_ok(self):
        result = self.backend.write('file1', b'hello world')
        assert result == {'status': 'ok'}

    def test_read_after_write(self):
        self.backend.write('file1', b'hello world')
        data = self.backend.read('file1')
        assert data == b'hello world'

    def test_write_then_read_binary(self):
        payload = bytes(range(256))
        self.backend.write('binary.bin', payload)
        assert self.backend.read('binary.bin') == payload

    def test_read_missing_file_raises(self):
        with pytest.raises(RuntimeError):
            self.backend.read('does-not-exist')

    def test_write_count_increments(self):
        api = self.backend.api
        assert api._write_count == 0
        self.backend.write('f1', b'data1')
        assert api._write_count == 1
        self.backend.write('f2', b'data2')
        assert api._write_count == 2

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def test_delete_existing_file(self):
        self.backend.write('to-delete', b'data')
        result = self.backend.delete('to-delete')
        assert result == {'status': 'ok'}

    def test_delete_removes_file(self):
        self.backend.write('to-delete', b'data')
        self.backend.delete('to-delete')
        with pytest.raises(RuntimeError):
            self.backend.read('to-delete')

    def test_delete_nonexistent_is_ok(self):
        result = self.backend.delete('ghost')
        assert result == {'status': 'ok'}

    # ------------------------------------------------------------------
    # list_files
    # ------------------------------------------------------------------

    def test_list_files_empty(self):
        files = self.backend.list_files()
        assert files == []

    def test_list_files_after_writes(self):
        self.backend.write('alpha', b'a')
        self.backend.write('beta',  b'b')
        files = self.backend.list_files()
        assert set(files) == {'alpha', 'beta'}

    def test_list_files_with_prefix(self):
        self.backend.write('data/obj1', b'a')
        self.backend.write('data/obj2', b'b')
        self.backend.write('refs/ref1', b'c')
        data_files = self.backend.list_files('data/')
        assert 'data/obj1' in data_files
        assert 'data/obj2' in data_files
        assert 'refs/ref1' not in data_files

    def test_list_files_different_vaults_isolated(self):
        api = Vault__API__In_Memory()
        api.setup()
        backend_a = Vault__Backend__API(api=api, vault_id='vaulta', write_key=VALID_WRITE_KEY)
        backend_b = Vault__Backend__API(api=api, vault_id='vaultb', write_key=VALID_WRITE_KEY)
        backend_a.write('shared-name', b'from-a')
        backend_b.write('shared-name', b'from-b')
        assert backend_a.read('shared-name') == b'from-a'
        assert backend_b.read('shared-name') == b'from-b'
        assert backend_a.list_files() == ['shared-name']
        assert backend_b.list_files() == ['shared-name']

    # ------------------------------------------------------------------
    # batch
    # ------------------------------------------------------------------

    def test_batch_write(self):
        ops = [{'op': 'write', 'file_id': 'f1',
                'data': base64.b64encode(b'data1').decode()}]
        result = self.backend.batch(ops)
        assert result['status'] == 'ok'
        assert self.backend.read('f1') == b'data1'

    def test_batch_multiple_writes(self):
        ops = [
            {'op': 'write', 'file_id': 'f1', 'data': base64.b64encode(b'aaa').decode()},
            {'op': 'write', 'file_id': 'f2', 'data': base64.b64encode(b'bbb').decode()},
        ]
        self.backend.batch(ops)
        assert self.backend.read('f1') == b'aaa'
        assert self.backend.read('f2') == b'bbb'

    def test_batch_delete(self):
        self.backend.write('del-me', b'data')
        ops = [{'op': 'delete', 'file_id': 'del-me'}]
        result = self.backend.batch(ops)
        assert result['status'] == 'ok'

    def test_batch_read(self):
        self.backend.write('r1', b'readable')
        ops = [{'op': 'read', 'file_id': 'r1'}]
        result = self.backend.batch(ops)
        assert result['status'] == 'ok'
        res_item = result['results'][0]
        assert res_item['status'] == 'ok'
        assert base64.b64decode(res_item['data']) == b'readable'

    def test_batch_read_missing(self):
        ops = [{'op': 'read', 'file_id': 'missing'}]
        result = self.backend.batch(ops)
        assert result['results'][0]['status'] == 'not_found'

    def test_batch_count_increments(self):
        api = self.backend.api
        assert api._batch_count == 0
        self.backend.batch([{'op': 'write', 'file_id': 'x',
                             'data': base64.b64encode(b'd').decode()}])
        assert api._batch_count == 1

    # ------------------------------------------------------------------
    # list_files — result normalisation (dict vs list path)
    # ------------------------------------------------------------------

    def test_list_files_returns_list(self):
        """list_files() must always return a plain list."""
        result = self.backend.list_files()
        assert isinstance(result, list)

    # ------------------------------------------------------------------
    # overwrite
    # ------------------------------------------------------------------

    def test_overwrite(self):
        self.backend.write('key', b'v1')
        self.backend.write('key', b'v2')
        assert self.backend.read('key') == b'v2'
