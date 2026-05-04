import hashlib
import json
import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.sync.Vault__Change_Pack     import Vault__Change_Pack
from sgit_ai.sync.Vault__GC              import Vault__GC
from sgit_ai.storage.Vault__Storage         import Vault__Storage
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from tests.unit.sync.vault_test_env      import Vault__Test_Env


class Test_Vault__GC:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        self.env       = self._env.restore()
        self.crypto    = self.env.crypto
        self.api       = self.env.api
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_gc_drain_no_pending(self):
        result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 0
        assert result['packs'] == []

    def test_gc_drain_with_pending_pack(self):
        self.sync.create_change_pack(self.directory, files={'new_file.txt': 'new content'})

        storage     = Vault__Storage()
        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        packs_before = change_pack.list_pending_packs(self.directory)
        assert len(packs_before) == 1

        result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 1

        packs_after = change_pack.list_pending_packs(self.directory)
        assert len(packs_after) == 0

    def test_gc_drain_copies_blobs_to_data(self):
        pack_result = self.sync.create_change_pack(self.directory, files={'test.txt': 'hello'})

        self.sync.gc_drain(self.directory)

        sg_dir    = os.path.join(self.directory, '.sg_vault')
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        blob_id   = pack_result['file_ids'][0]
        assert obj_store.exists(blob_id)

    def test_gc_drain_multiple_packs(self):
        self.sync.create_change_pack(self.directory, files={'a.txt': 'aaa'})
        self.sync.create_change_pack(self.directory, files={'b.txt': 'bbb'})

        result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 2

    def test_gc_drain_rejects_invalid_signature(self):
        pack_result = self.sync.create_change_pack(self.directory, files={'bad.txt': 'tampered'})
        pack_id = pack_result['pack_id']

        storage      = Vault__Storage()
        pending_dir  = storage.bare_pending_dir(self.directory)
        manifest_path = os.path.join(pending_dir, pack_id, 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        pki        = PKI__Crypto()
        bad_priv, _   = pki.generate_signing_key_pair()
        _, good_pub   = pki.generate_signing_key_pair()

        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub_pem = good_pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        fake_sig = pki.sign(bad_priv, manifest['payload_hash'].encode()).hex()
        manifest['signature']   = fake_sig
        manifest['creator_key'] = pub_pem
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 0

        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        assert len(change_pack.list_pending_packs(self.directory)) == 1

    def test_gc_drain_accepts_valid_signature(self):
        pki      = PKI__Crypto()
        priv_key, pub_key = pki.generate_signing_key_pair()

        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub_pem = pub_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        pack_result = self.sync.create_change_pack(self.directory, files={'signed.txt': 'valid data'})
        pack_id = pack_result['pack_id']

        storage       = Vault__Storage()
        pending_dir   = storage.bare_pending_dir(self.directory)
        manifest_path = os.path.join(pending_dir, pack_id, 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        valid_sig = pki.sign(priv_key, manifest['payload_hash'].encode()).hex()
        manifest['signature']   = valid_sig
        manifest['creator_key'] = pub_pem
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 1

    def test_create_change_pack_via_sync(self):
        result = self.sync.create_change_pack(self.directory, files={
            'file1.txt': 'content one',
            'file2.txt': 'content two'
        })
        assert result['pack_id'].startswith('pack-')
        assert len(result['file_ids']) == 2
        assert len(result['entries']) == 2

    def test_gc_drain_no_index_id_returns_early(self):
        """Line 46: drain_pending returns early when branch_index_file_id is None."""
        from sgit_ai.sync.Vault__GC import Vault__GC
        gc = Vault__GC(crypto=self.crypto, storage=Vault__Storage())
        result = gc.drain_pending(self.directory, b'\x00' * 32, 'some-branch',
                                  branch_index_file_id=None)
        assert result == dict(drained=0, packs=[])

    def test_gc_drain_no_branch_meta_returns_early(self):
        """Line 50: drain_pending returns early when branch not found in index."""
        from unittest.mock import patch, MagicMock
        from sgit_ai.sync.Vault__GC import Vault__GC
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        gc = Vault__GC(crypto=self.crypto, storage=Vault__Storage())
        with patch.object(Vault__Branch_Manager, 'load_branch_index', return_value=MagicMock()), \
             patch.object(Vault__Branch_Manager, 'get_branch_by_id', return_value=None):
            result = gc.drain_pending(self.directory, b'\x00' * 32, 'nonexistent',
                                      branch_index_file_id='fake-index-id')
        assert result == dict(drained=0, packs=[])

    def test_gc_drain_exception_in_loop_continues(self):
        """Lines 86-87: exception during pack processing silenced → drained=0."""
        from unittest.mock import patch
        from sgit_ai.sync.Vault__Change_Pack import Vault__Change_Pack
        self.sync.create_change_pack(self.directory, files={'temp.txt': 'temp'})
        with patch.object(Vault__Change_Pack, 'load_pack_manifest',
                          side_effect=RuntimeError('broken manifest')):
            result = self.sync.gc_drain(self.directory)
        assert result['drained'] == 0
