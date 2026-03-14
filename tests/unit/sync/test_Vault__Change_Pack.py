import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.sync.Vault__Change_Pack     import Vault__Change_Pack
from sg_send_cli.sync.Vault__Storage         import Vault__Storage


class Test_Vault__Change_Pack:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.storage = Vault__Storage()
        self.storage.create_bare_structure(self.tmp_dir)
        self.read_key = os.urandom(32)
        self.change_pack = Vault__Change_Pack(crypto=self.crypto, storage=self.storage)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_change_pack(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'hello.txt': 'hello world', 'data.bin': b'\x00\x01\x02'},
            branch_id='branch-clone-aa11bb22')

        assert result['pack_id'].startswith('pack-')
        assert len(result['file_ids']) == 2
        assert len(result['entries']) == 2
        assert os.path.isdir(result['pack_dir'])

    def test_list_pending_packs_empty(self):
        packs = self.change_pack.list_pending_packs(self.tmp_dir)
        assert packs == []

    def test_list_pending_packs_after_create(self):
        self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'a.txt': 'aaa'},
            branch_id='branch-clone-aa11bb33')
        self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'b.txt': 'bbb'},
            branch_id='branch-clone-aa11bb33')

        packs = self.change_pack.list_pending_packs(self.tmp_dir)
        assert len(packs) == 2
        assert all(p.startswith('pack-') for p in packs)

    def test_load_pack_manifest(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'test.txt': 'test content'},
            branch_id='branch-clone-aa11bb33')

        manifest = self.change_pack.load_pack_manifest(self.tmp_dir, result['pack_id'])
        assert manifest['schema'] == 'change_pack_v1'
        assert manifest['branch_id'] == 'branch-clone-aa11bb33'
        assert len(manifest['payload']) == 1

    def test_load_pack_blob(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'test.txt': 'test content'},
            branch_id='branch-clone-aa11bb33')

        blob_id = result['file_ids'][0]
        blob_data = self.change_pack.load_pack_blob(self.tmp_dir, result['pack_id'], blob_id)
        decrypted = self.crypto.decrypt(self.read_key, blob_data)
        assert decrypted == b'test content'

    def test_delete_pack(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'test.txt': 'content'},
            branch_id='branch-clone-aa11bb33')

        assert self.change_pack.delete_pack(self.tmp_dir, result['pack_id'])
        packs = self.change_pack.list_pending_packs(self.tmp_dir)
        assert packs == []

    def test_delete_nonexistent_pack(self):
        assert not self.change_pack.delete_pack(self.tmp_dir, 'pack-nonexistent')

    def test_change_pack_entries_have_content_hash(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'test.txt': 'hello'},
            branch_id='branch-clone-aa11bb33')

        entry = result['entries'][0]
        assert entry['path'] == 'test.txt'
        assert entry['content_hash']
        assert len(entry['content_hash']) == 12

    def test_change_pack_payload_hash(self):
        result = self.change_pack.create_change_pack(
            self.tmp_dir, self.read_key,
            files={'test.txt': 'hello'},
            branch_id='branch-clone-aa11bb33')

        manifest = self.change_pack.load_pack_manifest(self.tmp_dir, result['pack_id'])
        assert manifest['payload_hash']
        assert len(manifest['payload_hash']) == 64
