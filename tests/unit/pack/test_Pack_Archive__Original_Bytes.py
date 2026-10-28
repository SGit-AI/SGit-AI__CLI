"""Compaction archives a pack's original bytes (cli.build R3-1).

A pack written by 0.24.0 or 0.25.0 holds its members in id order; this build writes path order. Compaction
rebuilt the pack it archived in its own order and checked only the size, which the same members always
match, so the archive held other bytes under the same name and the archived index's offsets (`at`,
`tree_at`) pointed at other objects: `pack index verify` reported 64 bad offsets after the first compaction
of a vault 0.25.0 created. The scenario here is cli.build's `narrow.py`, with the older client's pack made by
rewriting the host's snapshot pack in id order."""
import io
import os
import shutil
import tempfile
import zipfile

from sgit_ai.core.Vault__Sync                        import Vault__Sync
from sgit_ai.core.actions.pack.Vault__Pack_Index     import Vault__Pack_Index
from sgit_ai.core.actions.pack.Vault__Pack_Maintain  import Vault__Pack_Maintain
from sgit_ai.core.actions.pack.Vault__Packs          import ZIP_EPOCH
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from tests._helpers.vault_test_env                   import TEST_VAULT_KEY


class Test_Pack_Archive__Original_Bytes:

    def setup_method(self):
        self.api  = Vault__API__In_Memory().setup()
        self.sync = Vault__Sync(crypto=Vault__Crypto(), api=self.api)
        self.root = tempfile.mkdtemp()
        self.a    = os.path.join(self.root, 'a')
        self.key  = self.sync.init(self.a, vault_key=TEST_VAULT_KEY, packs=True)['vault_key']
        for folder in ('raw/a', 'raw/b', 'docs', 'z'):                     # nested folders: path order != id order
            for i in range(15):
                path = os.path.join(self.a, folder, f'f{i}.txt')
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write(f'{folder} {i}\n')
        self.sync.commit(self.a, message='snapshot')
        self.sync.push(self.a)

    def teardown_method(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def indexer(self) -> Vault__Pack_Index:
        return Vault__Pack_Index(crypto=Vault__Crypto(), api=self.api)

    def rewrite_snapshot_in_id_order(self) -> str:
        """The host's snapshot pack, as 0.25.0 would have written it: the same members, the same size, id
        order; its index pack is dropped so `pack index build` backfills one for these bytes."""
        snapshot = [k for k in self.api._store if '/bare/packs/snapshots/' in k]
        assert len(snapshot) == 1
        key  = snapshot[0]
        old  = self.api._store[key]
        with zipfile.ZipFile(io.BytesIO(old)) as z:
            members = {i.filename: z.read(i) for i in z.infolist()}
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for name in sorted(members):
                info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_STORED
                z.writestr(info, members[name])
        new = out.getvalue()
        assert len(new) == len(old) and new != old                         # same size, other bytes
        self.api._store[key] = new
        for index_key in [k for k in self.api._store if '/bare/packs/indexes/snapshots/' in k]:
            del self.api._store[index_key]
        return key

    def test_compaction_archives_the_original_bytes_and_the_indexes_still_verify(self):
        key   = self.rewrite_snapshot_in_id_order()
        older = self.api._store[key]
        n     = os.path.join(self.root, 'n')
        self.sync.clone(self.key, n)
        with open(os.path.join(n, 'raw/a/f1.txt'), 'w') as f:
            f.write('edited\n')
        self.sync.commit(n, message='new')
        self.sync.push(n)
        self.indexer().build_missing(n)
        assert self.indexer().verify_indexes(n)['ok'] is True
        Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.api).compact(n)
        archived = [k for k in self.api._store if '/bare/packs/archive/' in k and k.endswith(key.rsplit('/', 1)[-1])]
        assert len(archived) == 1 and self.api._store[archived[0]] == older           # the original's bytes
        result = self.indexer().verify_indexes(n)
        assert result['ok'] is True and result['bad'] == [], result['bad'][:2]

    def test_a_pack_in_this_builds_order_is_still_rebuilt_not_downloaded(self):
        """The fast path is kept: a data pack whose rebuild matches its directory is not fetched whole
        (index packs are always fetched to be archived; they are small)."""
        key  = [k for k in self.api._store if '/bare/packs/snapshots/' in k][0]
        orig = self.api._store[key]
        n    = os.path.join(self.root, 'n')
        self.sync.clone(self.key, n)
        with open(os.path.join(n, 'docs/f1.txt'), 'w') as f:
            f.write('edited\n')
        self.sync.commit(n, message='new')
        self.sync.push(n)
        maintain = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.api)
        fetched  = []
        original_fetch = maintain.fetch_pack
        maintain.fetch_pack = lambda vault_id, entry: (fetched.append(entry['file_id']), original_fetch(vault_id, entry))[1]
        maintain.compact(n)
        archived = [k for k in self.api._store if '/bare/packs/archive/' in k and k.endswith(key.rsplit('/', 1)[-1])]
        assert self.api._store[archived[0]] == orig
        assert [f for f in fetched if '/indexes/' not in f] == []                   # data packs rebuilt, not downloaded
