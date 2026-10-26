"""Vault__Packs on its own: names, determinism, extraction with verification,
listing, absorbed records, object sets. All on a real local store."""
import io
import json
import os
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs      import (Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS,
                                                         PACK_BATCH_MAX, ZIP_EPOCH)
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from tests._helpers.pack_env                     import Pack__Env, Host__Counting
from tests._helpers.vault_test_env               import TEST_VAULT_KEY


class Test_Vault__Packs__Names:

    def test_pack_name_round_trips_through_parse_name(self):
        packs = Vault__Packs()
        name  = packs.pack_name('obj-cas-imm-0123456789ab', 12345, epoch_s=1700000000)
        assert name == '1700000000__obj-cas-imm-0123456789ab__12345.zip'
        info = packs.parse_name(name)
        assert info == dict(name=name, epoch=1700000000, commit_id='obj-cas-imm-0123456789ab', size=12345)
        assert packs.parse_name('bare/packs/commits/' + name)['name'] == name       # a path parses to its basename

    def test_parse_name_rejects_foreign_names(self):
        packs = Vault__Packs()
        for bad in ('notes.txt', '1700000000__x__1.zip', '17__obj-cas-imm-0123456789ab__1.zip',
                    '1700000000__obj-cas-imm-0123456789ab__x.zip', '1700000000__obj-cas-imm-0123456789ab__1.tar'):
            assert packs.parse_name(bad) is None, bad

    def test_pack_name_epoch_defaults_to_now_and_is_zero_padded(self):
        name = Vault__Packs().pack_name('obj-cas-imm-0123456789ab', 1)
        assert len(name.split('__')[0]) == 10 and name.split('__')[0].isdigit()


class Test_Vault__Packs__Zip_Bytes:

    def setup_method(self):
        self.env   = Pack__Env()
        self.sync, self.vault, self.key = self.env.pack_vault(self.env.text_files(5), vault_key=TEST_VAULT_KEY)
        self.sg    = os.path.join(self.vault, '.sg_vault')
        self.packs = Vault__Packs(crypto=self.sync.crypto, api=self.env.api)
        c          = self.sync._init_components(self.vault)
        self.rk    = c.read_key
        self.head  = c.ref_manager.read_ref(c.ref_file_id, c.read_key)

    def test_write_pack_is_deterministic(self):
        ids = self.packs.reachable_objects(self.sg, self.head, self.rk)
        a   = os.path.join(self.env.root, 'a.zip'); b = os.path.join(self.env.root, 'b.zip')
        self.packs.write_pack(self.sg, ids, a)
        self.packs.write_pack(self.sg, list(reversed(ids)), b)                  # order of the input does not matter
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            assert fa.read() == fb.read()
        with zipfile.ZipFile(a) as z:
            infos = z.infolist()
            assert [i.filename for i in infos] == [f'bare/data/{i}' for i in sorted(ids)]
            assert all(i.date_time == ZIP_EPOCH and i.compress_type == zipfile.ZIP_STORED for i in infos)

    def test_write_pack_skips_ids_not_in_the_store(self):
        out = os.path.join(self.env.root, 'c.zip')
        self.packs.write_pack(self.sg, ['obj-cas-imm-000000000000'] + self.packs.reachable_objects(self.sg, self.head, self.rk)[:1], out)
        with zipfile.ZipFile(out) as z:
            assert len(z.namelist()) == 1

    def test_members_of_lists_object_ids(self):
        ids = self.packs.reachable_objects(self.sg, self.head, self.rk)
        out = os.path.join(self.env.root, 'd.zip')
        self.packs.write_pack(self.sg, ids, out)
        with open(out, 'rb') as f:
            assert self.packs.members_of(f.read()) == sorted(ids)

    def test_extract_pack_writes_verified_members_into_a_fresh_store(self):
        ids = self.packs.reachable_objects(self.sg, self.head, self.rk)
        out = os.path.join(self.env.root, 'e.zip')
        self.packs.write_pack(self.sg, ids, out)
        other = os.path.join(self.env.root, 'other', '.sg_vault')
        os.makedirs(os.path.join(other, 'bare', 'data'))
        with open(out, 'rb') as f:
            result = self.packs.extract_pack(f.read(), other, self.rk)
        assert result == dict(extracted=len(ids), refused=[], objects=sorted(ids))
        assert sorted(os.listdir(os.path.join(other, 'bare', 'data'))) == sorted(ids)
        assert self.env.store_bytes(os.path.join(self.env.root, 'other')) == {k: v for k, v in self.env.store_bytes(self.vault).items() if k in ids}

    def test_extract_pack_refuses_a_tampered_member_and_writes_nothing_for_it(self):
        ids = self.packs.reachable_objects(self.sg, self.head, self.rk)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            store = Vault__Object_Store(vault_path=self.sg, crypto=self.sync.crypto)
            good  = ids[0]
            z.writestr(f'bare/data/{good}', store.load(good))
            z.writestr(f'bare/data/{ids[1]}', store.load(ids[1]) + b'x')          # bytes that do not hash to the id
            z.writestr(f'bare/data/obj-cas-imm-deadbeefdead', b'forged object')      # an id nothing hashes to
        other = os.path.join(self.env.root, 'tampered', '.sg_vault')
        os.makedirs(os.path.join(other, 'bare', 'data'))
        result = self.packs.extract_pack(buf.getvalue(), other, self.rk)
        assert result['extracted'] == 1
        assert sorted(result['refused']) == sorted([f'bare/data/{ids[1]}', 'bare/data/obj-cas-imm-deadbeefdead'])
        assert os.listdir(os.path.join(other, 'bare', 'data')) == [good]

    def test_extract_pack_refuses_members_outside_bare_data(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('../../escape', b'x')
            z.writestr('bare/refs/ref-pid-muw-000000000000', b'x')
            z.writestr('bare/data/../keys/key', b'x')
        other = os.path.join(self.env.root, 'outside', '.sg_vault')
        os.makedirs(os.path.join(other, 'bare', 'data'))
        result = self.packs.extract_pack(buf.getvalue(), other, self.rk)
        assert result['extracted'] == 0 and len(result['refused']) == 3
        assert os.listdir(os.path.join(other, 'bare', 'data')) == []
        assert not os.path.exists(os.path.join(other, 'bare', 'refs', 'ref-pid-muw-000000000000'))
        assert not os.path.exists(os.path.join(self.env.root, 'escape'))

    def test_objects_introduced_by_a_commit_excludes_what_its_parents_reach(self):
        self.env.write(self.vault, {'new.md': 'brand new\n' * 20})
        new_head = self.sync.commit(self.vault, message='second')['commit_id']
        intro    = self.packs.objects_introduced(self.sg, new_head, self.rk)
        parents  = self.packs.objects_of_commit(self.sg, self.head, self.rk)
        assert new_head in intro
        assert not (set(intro) & parents)
        assert set(intro) == self.packs.objects_of_commit(self.sg, new_head, self.rk) - parents
        assert self.packs.reachable_commits(self.sg, new_head, self.rk) >= {new_head, self.head}

    def test_commit_pack_name_carries_the_size_of_its_bytes(self):
        path, name = self.packs.build_commit_pack(self.sg, self.head, self.rk, os.path.join(self.env.root, 'w'))
        assert self.packs.parse_name(name)['size'] == os.path.getsize(path)
        assert self.packs.parse_name(name)['commit_id'] == self.head


class Test_Vault__Packs__Host:

    def setup_method(self):
        self.api   = Host__Counting().setup()
        self.packs = Vault__Packs(crypto=Vault__Crypto(), api=self.api)

    def test_list_folder_is_oldest_first_and_ignores_foreign_names(self):
        v = 'vault1'
        self.api._store[f'{v}/{PACK_COMMITS}1700000002__obj-cas-imm-aaaaaaaaaaaa__10.zip'] = b'0' * 10
        self.api._store[f'{v}/{PACK_COMMITS}1700000001__obj-cas-imm-bbbbbbbbbbbb__20.zip'] = b'0' * 20
        self.api._store[f'{v}/{PACK_COMMITS}README.txt']                                   = b'not a pack'
        self.api._store[f'{v}/{PACK_SNAPSHOTS}1700000000__obj-cas-imm-cccccccccccc__30.zip'] = b'0' * 30
        listed = self.packs.list_folder(v, PACK_COMMITS)
        assert [e['commit_id'] for e in listed] == ['obj-cas-imm-bbbbbbbbbbbb', 'obj-cas-imm-aaaaaaaaaaaa']
        assert listed[0]['file_id'] == f'{PACK_COMMITS}1700000001__obj-cas-imm-bbbbbbbbbbbb__20.zip'
        assert [e['size'] for e in self.packs.list_folder(v, PACK_SNAPSHOTS)] == [30]

    def test_fetch_pack_refuses_bytes_whose_length_disagrees_with_the_name(self):
        v = 'vault2'
        self.api._store[f'{v}/{PACK_COMMITS}1700000001__obj-cas-imm-bbbbbbbbbbbb__20.zip'] = b'0' * 19
        entry = self.packs.list_folder(v, PACK_COMMITS)[0]
        with pytest.raises(RuntimeError, match='expected 20 bytes, got 19'):
            self.packs.fetch_pack(v, entry)

    def test_fetch_packs_groups_small_packs_into_one_batch_read(self):
        v = 'vault3'
        for i in range(5):
            self.api._store[f'{v}/{PACK_COMMITS}17000000{i:02d}__obj-cas-imm-{i:012d}__100.zip'] = bytes([i]) * 100
        entries = self.packs.list_folder(v, PACK_COMMITS)
        self.api.reset_counts()
        got = self.packs.fetch_packs(v, entries)
        assert self.api.calls['batch_read'] == 1 and self.api.requests() == 1
        assert sorted(got) == sorted(e['name'] for e in entries) and all(len(b) == 100 for b in got.values())

    def test_fetch_packs_reads_a_large_pack_on_its_own(self):
        v = 'vault4'
        big = PACK_BATCH_MAX + 1
        self.api._store[f'{v}/{PACK_COMMITS}1700000001__obj-cas-imm-aaaaaaaaaaaa__{big}.zip'] = b'0' * big
        self.api._store[f'{v}/{PACK_COMMITS}1700000002__obj-cas-imm-bbbbbbbbbbbb__5.zip']     = b'0' * 5
        self.api.reset_counts()
        got = self.packs.fetch_packs(v, self.packs.list_folder(v, PACK_COMMITS))
        assert len(got) == 2 and self.api.calls['read_large'] == 1 and self.api.calls['batch_read'] == 1

    def test_absorbed_record_is_a_set_on_disk(self):
        env = Pack__Env(self.api)
        d   = env.path()
        os.makedirs(os.path.join(d, '.sg_vault', 'local'))
        assert self.packs.load_absorbed(d) == set()
        self.packs.record_absorbed(d, ['b.zip', 'a.zip'])
        self.packs.record_absorbed(d, ['a.zip', 'c.zip'])
        assert self.packs.load_absorbed(d) == {'a.zip', 'b.zip', 'c.zip'}
        with open(os.path.join(d, '.sg_vault', 'local', 'packs_absorbed.json')) as f:
            assert json.load(f) == {'packs': ['a.zip', 'b.zip', 'c.zip']}
