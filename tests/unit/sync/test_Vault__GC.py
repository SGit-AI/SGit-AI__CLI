import hashlib
import json
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.crypto.PKI__Crypto          import PKI__Crypto
from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.sync.Vault__Change_Pack     import Vault__Change_Pack
from sg_send_cli.sync.Vault__GC              import Vault__GC
from sg_send_cli.sync.Vault__Storage         import Vault__Storage
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store


class Test_Vault__GC:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='gc-test'):
        directory = os.path.join(self.tmp_dir, name)
        result    = self.sync.init(directory)
        return result, directory

    def test_gc_drain_no_pending(self):
        _, directory = self._init_vault()
        result = self.sync.gc_drain(directory)
        assert result['drained'] == 0
        assert result['packs'] == []

    def test_gc_drain_with_pending_pack(self):
        _, directory = self._init_vault()
        self.sync.create_change_pack(directory, files={'new_file.txt': 'new content'})

        storage     = Vault__Storage()
        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        packs_before = change_pack.list_pending_packs(directory)
        assert len(packs_before) == 1

        result = self.sync.gc_drain(directory)
        assert result['drained'] == 1

        packs_after = change_pack.list_pending_packs(directory)
        assert len(packs_after) == 0

    def test_gc_drain_copies_blobs_to_data(self):
        _, directory = self._init_vault()
        pack_result = self.sync.create_change_pack(directory, files={'test.txt': 'hello'})

        self.sync.gc_drain(directory)

        sg_dir    = os.path.join(directory, '.sg_vault')
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        blob_id   = pack_result['file_ids'][0]
        assert obj_store.exists(blob_id)

    def test_gc_drain_multiple_packs(self):
        _, directory = self._init_vault()
        self.sync.create_change_pack(directory, files={'a.txt': 'aaa'})
        self.sync.create_change_pack(directory, files={'b.txt': 'bbb'})

        result = self.sync.gc_drain(directory)
        assert result['drained'] == 2

    def test_gc_drain_rejects_invalid_signature(self):
        _, directory = self._init_vault()
        pack_result = self.sync.create_change_pack(directory, files={'bad.txt': 'tampered'})
        pack_id = pack_result['pack_id']

        storage      = Vault__Storage()
        pending_dir  = storage.bare_pending_dir(directory)
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

        result = self.sync.gc_drain(directory)
        assert result['drained'] == 0

        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=storage)
        assert len(change_pack.list_pending_packs(directory)) == 1

    def test_gc_drain_accepts_valid_signature(self):
        _, directory = self._init_vault()

        pki      = PKI__Crypto()
        priv_key, pub_key = pki.generate_signing_key_pair()

        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        pub_pem = pub_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

        pack_result = self.sync.create_change_pack(directory, files={'signed.txt': 'valid data'})
        pack_id = pack_result['pack_id']

        storage       = Vault__Storage()
        pending_dir   = storage.bare_pending_dir(directory)
        manifest_path = os.path.join(pending_dir, pack_id, 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        valid_sig = pki.sign(priv_key, manifest['payload_hash'].encode()).hex()
        manifest['signature']   = valid_sig
        manifest['creator_key'] = pub_pem
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        result = self.sync.gc_drain(directory)
        assert result['drained'] == 1

    def test_create_change_pack_via_sync(self):
        _, directory = self._init_vault()
        result = self.sync.create_change_pack(directory, files={
            'file1.txt': 'content one',
            'file2.txt': 'content two'
        })
        assert result['pack_id'].startswith('pack-')
        assert len(result['file_ids']) == 2
        assert len(result['entries']) == 2
