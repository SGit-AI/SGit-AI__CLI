"""The round trip on disk: a normal vault -> `pack import` -> a pack vault -> push ->
clone -> `pack export` -> a normal vault -> push -> clone. At every stage the working
copy is identical, the history is the same length with the same messages and
timestamps, every object id is the content address of its bytes, every commit is
signed by the new clone's key and verifies, and the source vault is untouched."""
import json
import os

import pytest

from sgit_ai.core.actions.pack.Vault__Pack_Convert import Vault__Pack_Convert
from sgit_ai.core.actions.pack.Vault__Packs        import Vault__Packs, PACK_SNAPSHOTS
from sgit_ai.crypto.PKI__Crypto                    import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto, DEFLATE_MAGIC
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from sgit_ai.storage.Vault__Format                 import Vault__Format, FEATURE_PACKS, FEATURE_BLOB_DEFLATE
from tests._helpers.pack_env                       import Pack__Env
from tests._helpers.vault_test_env                 import TEST_VAULT_KEYS


def _history(sync, directory) -> list:
    """[(message, timestamp_ms, signed_and_verified, author_key_id)] head first."""
    c   = sync._init_components(directory)
    vc  = Vault__Commit(crypto=sync.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
    cfg = sync._read_local_config(directory, c.storage)
    idx = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
    meta= c.branch_manager.get_branch_by_id(idx, str(cfg.my_branch_id))
    cid = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
    out = []
    while cid:
        commit  = vc.load_commit(cid, c.read_key)
        message = sync.crypto.decrypt_metadata(c.read_key, str(commit.message_enc)) if commit.message_enc else ''
        ok      = False
        if commit.author_key_id:
            ok = vc.verify_commit_signature(commit, c.key_manager.load_public_key(str(commit.author_key_id), c.read_key))
        out.append((message, int(commit.timestamp_ms), ok, str(commit.author_key_id or '')))
        cid = str(commit.parents[0]) if commit.parents else ''
    return out


def _ids_are_content_addresses(store: dict) -> bool:
    crypto = Vault__Crypto()
    return all(crypto.compute_object_id(data, len(oid) - len('obj-cas-imm-')) == oid for oid, data in store.items())


class Test_Pack_Convert__Round_Trip:

    def setup_method(self):
        self.env  = Pack__Env()
        self.sync, self.normal, _ = self.env.normal_vault(self.env.text_files(4, 'a'), vault_key=TEST_VAULT_KEYS[0], message='one')
        self.env.write(self.normal, self.env.text_files(3, 'b', salt='second ')); self.sync.commit(self.normal, message='two')
        self.env.write(self.normal, {'a0.md': b'rewritten\n' * 50, 'bin/noise.bin': os.urandom(4000)})
        self.sync.commit(self.normal, message='three')
        self.env.delete(self.normal, 'b1.md'); self.sync.commit(self.normal, message='four', allow_deletions=True)
        self.sync.push(self.normal)
        self.files   = self.env.tree(self.normal)
        self.history = _history(self.sync, self.normal)
        self.source_store_before = self.env.store_bytes(self.normal)

    def test_import_then_export_keeps_the_working_copy_history_and_content_addresses(self):
        conv   = Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api)
        packed = self.env.path('packed')
        stats  = conv.convert(self.normal, packed, packs=True, vault_key=TEST_VAULT_KEYS[1])
        assert self.env.tree(packed) == self.files
        assert stats['commits'] == len(self.history) and stats['blobs'] >= 8 and stats['deflated'] >= 7
        sync_p  = self.env.sync()
        hist_p  = _history(sync_p, packed)
        assert [(m, t) for m, t, _, _ in hist_p] == [(m, t) for m, t, _, _ in self.history]
        assert all(ok for _, _, ok, _ in hist_p) and len({k for _, _, _, k in hist_p}) == 1   # re-signed by the one new key
        index_p = sync_p._init_components(packed).branch_manager.load_branch_index(
            packed, sync_p._init_components(packed).branch_index_file_id, sync_p._init_components(packed).read_key)
        assert {FEATURE_PACKS, FEATURE_BLOB_DEFLATE} <= set(Vault__Format().features_of(index_p))
        assert _ids_are_content_addresses(self.env.store_bytes(packed))
        assert self.env.store_bytes(self.normal) == self.source_store_before         # the source is untouched
        assert self.env.tree(self.normal) == self.files
        # status before the first push: the history IS the vault's (not work on top of it): nothing behind
        st = sync_p.status(packed)
        assert (st['ahead'], st['behind']) == (0, 0)
        assert sync_p.push(packed)['status'] == 'pushed'
        vid_p = sync_p._init_components(packed).vault_id
        assert self.env.api.loose_objects(vid_p) == [] and len(self.env.api.packs(vid_p, PACK_SNAPSHOTS)) == 1
        sync_pc, packed_clone = self.env.clone(stats['vault_key'], 'packed-clone')
        assert self.env.tree(packed_clone) == self.files
        assert [(m, t) for m, t, _, _ in _history(sync_pc, packed_clone)] == [(m, t) for m, t, _, _ in self.history]

        exported = self.env.path('exported')
        stats_e  = Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api).convert(
            packed_clone, exported, packs=False, vault_key=TEST_VAULT_KEYS[2])
        assert self.env.tree(exported) == self.files
        sync_e = self.env.sync()
        hist_e = _history(sync_e, exported)
        assert [(m, t) for m, t, _, _ in hist_e] == [(m, t) for m, t, _, _ in self.history]
        assert all(ok for _, _, ok, _ in hist_e)
        assert stats_e['deflated'] == 0
        assert not [n for n, b in self.env.store_bytes(exported).items() if b.startswith(DEFLATE_MAGIC)]
        assert Vault__Format().features_of(sync_e._init_components(exported).branch_manager.load_branch_index(
            exported, sync_e._init_components(exported).branch_index_file_id, sync_e._init_components(exported).read_key)) == []
        assert _ids_are_content_addresses(self.env.store_bytes(exported))
        assert sync_e.push(exported)['status'] == 'pushed'
        vid_e = sync_e._init_components(exported).vault_id
        assert len(self.env.api.loose_objects(vid_e)) >= stats_e['commits'] + stats_e['trees'] + stats_e['blobs']
        assert self.env.api.packs(vid_e) == []
        sync_ec, exported_clone = self.env.clone(stats_e['vault_key'], 'exported-clone')
        assert self.env.tree(exported_clone) == self.files
        assert [(m, t) for m, t, _, _ in _history(sync_ec, exported_clone)] == [(m, t) for m, t, _, _ in self.history]
        # three different vaults, three different keys: no object or ref is shared on the host
        vid_n = self.sync._init_components(self.normal).vault_id
        assert len({vid_n, vid_p, vid_e}) == 3
        assert not set(self.env.api.host_files(vid_n)) & set(self.env.api.host_files(vid_p))

    def test_import_without_deflate_keeps_every_blob_in_the_v1_envelope(self):
        packed = self.env.path('packed-plain')
        stats  = Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api).convert(
            self.normal, packed, packs=True, vault_key=TEST_VAULT_KEYS[1], deflate=False)
        assert stats['deflated'] == 0 and self.env.tree(packed) == self.files
        assert not [n for n, b in self.env.store_bytes(packed).items() if b.startswith(DEFLATE_MAGIC)]
        sync_p = self.env.sync()
        assert FEATURE_PACKS in Vault__Format().features_of(sync_p._init_components(packed).branch_manager.load_branch_index(
            packed, sync_p._init_components(packed).branch_index_file_id, sync_p._init_components(packed).read_key))

    def test_compression_stats_are_measured_on_the_blobs(self):
        packed = self.env.path('packed-stats')
        stats  = Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api).convert(
            self.normal, packed, packs=True, vault_key=TEST_VAULT_KEYS[1])
        assert stats['blob_cipher_bytes_target'] < stats['blob_cipher_bytes_source']
        assert stats['blob_ratio'] > 2.0                                            # prose-like text: deflate bites hard
        assert stats['blob_plain_bytes'] > 0 and stats['elapsed_s'] >= 0
        assert stats['target_head'] != stats['source_head']

    def test_convert_refuses_a_target_that_is_already_a_vault(self):
        with pytest.raises(RuntimeError, match='already a vault'):
            Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api).convert(
                self.normal, self.normal, packs=True, vault_key=TEST_VAULT_KEYS[1])

    def test_the_two_clones_of_an_imported_vault_keep_working_together(self):
        packed = self.env.path('packed-work')
        stats  = Vault__Pack_Convert(crypto=Vault__Crypto(), api=self.env.api).convert(
            self.normal, packed, packs=True, vault_key=TEST_VAULT_KEYS[1])
        sync_p = self.env.sync(); sync_p.push(packed)
        sync_x, x = self.env.clone(stats['vault_key'], 'x')
        sync_y, y = self.env.clone(stats['vault_key'], 'y')
        self.env.write(x, {'x.md': b'x\n' * 20}); sync_x.commit(x, message='x'); sync_x.push(x)
        self.env.write(y, {'y.md': b'y\n' * 20}); sync_y.commit(y, message='y'); sync_y.push(y)
        sync_x.pull(x); sync_p.pull(packed)
        assert self.env.tree(x) == self.env.tree(y) == self.env.tree(packed)
        assert self.env.api.loose_objects(sync_p._init_components(packed).vault_id) == []
