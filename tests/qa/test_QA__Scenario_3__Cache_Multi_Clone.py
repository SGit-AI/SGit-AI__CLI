"""QA Scenario 3: Cache layer across multiple clones.

The cache layer's hard properties are cross-client ones, and none of them can be
proven inside a single working copy. This scenario runs a realistic multi-clone
workflow — one origin, two clones in separate folders, pushes and pulls flowing
both ways — and asserts the behaviours the design commits to:

  - a clone made AFTER a cache exists needs no cache awareness to work (D6)
  - clone B heals a cache declared by clone A, because targets come from the
    server listing rather than the local mirror (D6)
  - content flows correctly in both directions with caches present
  - a delete on one clone removes the cache everywhere
  - caches survive a clone that never touches them
  - reading works from read_key alone, with no clone at all (contract §4.2)
  - correctness never depends on the cache: with every cache object deleted from
    the server, both clones still read the right content

Self-contained: uses Vault__API__In_Memory (no external server required).

Run:
    pytest tests/qa/test_QA__Scenario_3__Cache_Multi_Clone.py -s -v
"""
import base64
import os
import shutil
import tempfile

import pytest

pytestmark = pytest.mark.qa

from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.cache.Vault__Cache_Reader import Vault__Cache_Reader
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.storage.Vault__Storage                 import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager           import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind            import Enum__Cache_Kind
from sgit_ai.cli.CLI__Cache                         import CLI__Cache


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Workspace:
    """One origin vault plus clones in sibling folders, all against one API."""

    def __init__(self):
        self.tmp     = tempfile.mkdtemp(prefix='sg_qa_scenario3_')
        self.api     = Vault__API__In_Memory().setup()
        self.crypto  = Vault__Crypto()
        self.storage = Vault__Storage()
        self.manager = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)

        self.origin  = os.path.join(self.tmp, 'origin')
        init         = self.sync().init(self.origin)
        self.vault_key = init['vault_key']
        self.vault_id  = init['vault_id']
        self.read_key  = self.crypto.derive_keys_from_vault_key(self.vault_key)['read_key_bytes']

    def sync(self):
        return Vault__Sync(crypto=Vault__Crypto(), api=self.api)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, vault_dir, rel, text):
        p = os.path.join(vault_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def read(self, vault_dir, rel):
        with open(os.path.join(vault_dir, rel)) as f:
            return f.read()

    def clone_into(self, name):
        target = os.path.join(self.tmp, name)
        self.sync().clone(self.vault_key, target)
        return target

    def declare(self, vault_dir, path, kind=Enum__Cache_Kind.VALUE, capsys=None):
        CLI__Cache().cmd_cache_add(_Args(path=path, directory=vault_dir,
                                         pointer=(kind == Enum__Cache_Kind.POINTER),
                                         value=(kind == Enum__Cache_Kind.VALUE)))
        if capsys:
            capsys.readouterr()

    def cache_id(self, path, kind=Enum__Cache_Kind.VALUE):
        return self.manager.cache_id(self.read_key, self.vault_id, path, kind)

    def server_cache_files(self):
        return [str(f) for f in (self.api.list_files(self.vault_id, 'bare/cache/') or [])]

    def read_cache_from_server(self, path, kind=Enum__Cache_Kind.VALUE):
        cid  = self.cache_id(path, kind)
        fid  = self.manager.file_id(kind, cid)
        data = self.api.batch_read(self.vault_id, [fid])
        if not data.get(fid):
            return None
        return self.manager.decrypt_object(data[fid], self.read_key, kind)


@pytest.fixture()
def ws():
    w = _Workspace()
    yield w
    w.cleanup()


class Test_QA__S3__A__Clone_After_Cache_Exists:
    """A clone made after caches exist needs no cache awareness (D6)."""

    def test_clone_succeeds_and_content_is_correct(self, ws, capsys):
        ws.write(ws.origin, 'pages/home.md', '# Home\n')
        ws.write(ws.origin, 'media/a.txt',   'photo-a')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)

        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.declare(ws.origin, 'media',         Enum__Cache_Kind.POINTER, capsys)
        ws.sync().push(ws.origin)
        assert len(ws.server_cache_files()) == 2, 'caches were not published'

        clone_b = ws.clone_into('clone_b')
        assert ws.read(clone_b, 'pages/home.md') == '# Home\n'
        assert ws.read(clone_b, 'media/a.txt')   == 'photo-a'

    def test_clone_does_not_download_cache_objects(self, ws, capsys):
        # clone fetches by known id and never enumerates bare/cache/ — the local
        # mirror of a fresh clone is deliberately empty.
        ws.write(ws.origin, 'pages/home.md', '# Home\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        assert ws.manager.list_all(clone_b) == []
        assert len(ws.server_cache_files()) == 1        # still present on the server


class Test_QA__S3__B__Cross_Clone_Healing:
    """Clone B heals a cache clone A declared, without ever declaring it (D6)."""

    def test_edit_on_b_heals_a_declared_cache(self, ws, capsys):
        ws.write(ws.origin, 'pages/home.md', '# Home v1\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        assert ws.manager.list_all(clone_b) == []       # B knows nothing about caches

        ws.write(clone_b, 'pages/home.md', '# Home v2 (from B)\n')
        ws.sync().commit(clone_b, 'edit from B')
        result = ws.sync().push(clone_b)

        assert result['cache_updated'] >= 1, 'B did not reconcile A-declared caches'
        obj = ws.read_cache_from_server('pages/home.md')
        assert obj is not None
        assert base64.b64decode(str(obj.value_b64)) == b'# Home v2 (from B)\n'

    def test_a_pulls_and_sees_bs_content_and_fresh_cache(self, ws, capsys):
        ws.write(ws.origin, 'pages/home.md', '# Home v1\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        ws.write(clone_b, 'pages/home.md', '# Home v2 (from B)\n')
        ws.sync().commit(clone_b, 'edit from B')
        ws.sync().push(clone_b)

        ws.sync().pull(ws.origin)
        assert ws.read(ws.origin, 'pages/home.md') == '# Home v2 (from B)\n'
        assert ws.sync().sparse_cat(ws.origin, 'pages/home.md') == b'# Home v2 (from B)\n'


class Test_QA__S3__C__Three_Way_Round_Trip:
    """Origin + two clones in separate folders, changes flowing both ways."""

    def test_round_trip_across_three_working_copies(self, ws, capsys):
        ws.write(ws.origin, 'pages/home.md',  '# Home v1\n')
        ws.write(ws.origin, 'keys/api.json',  '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        clone_c = ws.clone_into('clone_c')

        # B changes the cached record
        ws.write(clone_b, 'keys/api.json', '{"k":"v2-from-B"}')
        ws.sync().commit(clone_b, 'B updates key')
        ws.sync().push(clone_b)

        # C pulls, sees B's change, then adds an unrelated file
        ws.sync().pull(clone_c)
        assert ws.read(clone_c, 'keys/api.json') == '{"k":"v2-from-B"}'
        ws.write(clone_c, 'pages/about.md', '# About\n')
        ws.sync().commit(clone_c, 'C adds a page')
        ws.sync().push(clone_c)

        # origin pulls and sees both
        ws.sync().pull(ws.origin)
        assert ws.read(ws.origin, 'keys/api.json')  == '{"k":"v2-from-B"}'
        assert ws.read(ws.origin, 'pages/about.md') == '# About\n'

        # the cache tracks the latest content and the current head
        obj = ws.read_cache_from_server('keys/api.json')
        assert base64.b64decode(str(obj.value_b64)) == b'{"k":"v2-from-B"}'

    def test_cache_survives_a_clone_that_never_touches_it(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'docs/read.md',  '# Docs\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        ws.write(clone_b, 'docs/read.md', '# Docs v2\n')     # unrelated file
        ws.sync().commit(clone_b, 'B edits docs')
        ws.sync().push(clone_b)

        obj = ws.read_cache_from_server('keys/api.json')
        assert obj is not None, 'an unrelated push destroyed the cache'
        assert base64.b64decode(str(obj.value_b64)) == b'{"k":"v1"}'


class Test_QA__S3__D__Deletion_Propagates:

    def test_delete_on_one_clone_removes_the_cache_everywhere(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'docs/read.md',  '# Docs\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)
        assert len(ws.server_cache_files()) == 1

        clone_b = ws.clone_into('clone_b')
        os.remove(os.path.join(clone_b, 'keys/api.json'))
        ws.sync().commit(clone_b, 'B deletes the key', allow_deletions=True)
        result = ws.sync().push(clone_b)

        assert result['cache_deleted'] >= 1
        assert ws.read_cache_from_server('keys/api.json') is None
        assert ws.server_cache_files() == []


class Test_QA__S3__E__Read_Without_A_Clone:
    """The §4.2 capability: read_key alone, no working copy anywhere."""

    def test_reader_resolves_from_read_key_only(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"hot-record"}')
        ws.write(ws.origin, 'media/a.txt',   'photo-a')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.declare(ws.origin, 'media',         Enum__Cache_Kind.POINTER, capsys)
        ws.sync().push(ws.origin)

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=ws.api)

        value = reader.read_path(ws.vault_id, ws.read_key, 'keys/api.json')
        assert value['fresh']       is True
        assert value['content']     == b'{"k":"hot-record"}'
        assert value['round_trips'] == 1

        folder = reader.read_path(ws.vault_id, ws.read_key, 'media')
        assert folder['target_kind'] == 'tree'
        assert folder['round_trips'] == 1

    def test_reader_sees_updates_pushed_by_another_clone(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        ws.write(clone_b, 'keys/api.json', '{"k":"v2-from-B"}')
        ws.sync().commit(clone_b, 'B updates')
        ws.sync().push(clone_b)

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=ws.api)
        result = reader.read_path(ws.vault_id, ws.read_key, 'keys/api.json')
        assert result['fresh']   is True
        assert result['content'] == b'{"k":"v2-from-B"}'


class Test_QA__S3__F__Correctness_Without_The_Cache:
    """The floor: wiping every cache object must change no answer."""

    def test_all_clones_still_read_correctly_with_caches_destroyed(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'pages/home.md', '# Home\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')

        # nuke every cache object, locally and on the server
        for kind, cid in list(ws.manager.list_all(ws.origin)):
            ws.manager.delete(ws.origin, kind, cid)
            ws.api.delete(ws.vault_id, ws.manager.file_id(kind, cid), 'x')
        assert ws.server_cache_files() == []

        assert ws.sync().sparse_cat(ws.origin,  'keys/api.json') == b'{"k":"v1"}'
        assert ws.sync().sparse_cat(clone_b,    'keys/api.json') == b'{"k":"v1"}'
        assert ws.read(clone_b, 'pages/home.md') == '# Home\n'

        # and a normal push/pull cycle still works with no caches at all
        ws.write(clone_b, 'pages/home.md', '# Home v2\n')
        ws.sync().commit(clone_b, 'edit')
        ws.sync().push(clone_b)
        ws.sync().pull(ws.origin)
        assert ws.read(ws.origin, 'pages/home.md') == '# Home v2\n'


class Test_QA__S3__G__Rm_Does_Not_Resurrect:
    """`cache rm` must stick: without tombstones the next push rediscovered the
    server copy via the D6 listing and resurrected it (review 08/14 #1)."""

    def _declared_and_pushed(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'docs/read.md',  '# Docs\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)
        assert len(ws.server_cache_files()) == 1

    def test_rm_then_push_deletes_the_server_copy(self, ws, capsys):
        self._declared_and_pushed(ws, capsys)
        CLI__Cache().cmd_cache_rm(_Args(path='keys/api.json', directory=ws.origin))
        capsys.readouterr()
        result = ws.sync().push(ws.origin)                     # up-to-date push
        assert result['cache_deleted'] >= 1
        assert ws.server_cache_files() == []
        # tombstone consumed — nothing left to re-delete
        assert ws.manager.tombstoned_ids(ws.origin) == set()

    def test_no_resurrection_on_subsequent_pushes(self, ws, capsys):
        self._declared_and_pushed(ws, capsys)
        CLI__Cache().cmd_cache_rm(_Args(path='keys/api.json', directory=ws.origin))
        capsys.readouterr()
        ws.sync().push(ws.origin)
        # further pushes — including ones that carry commits — must not bring it back
        ws.write(ws.origin, 'docs/read.md', '# Docs v2\n')
        ws.sync().commit(ws.origin, 'edit docs')
        result = ws.sync().push(ws.origin)
        assert result.get('cache_updated', 0) == 0
        assert ws.server_cache_files() == []
        assert ws.manager.list_all(ws.origin) == []

    def test_clone_b_can_remove_a_cache_clone_a_declared(self, ws, capsys):
        self._declared_and_pushed(ws, capsys)
        clone_b = ws.clone_into('clone_b')
        assert ws.manager.list_all(clone_b) == []              # nothing local on B
        CLI__Cache().cmd_cache_rm(_Args(path='keys/api.json', directory=clone_b))
        assert 'removal recorded' in capsys.readouterr().out
        result = ws.sync().push(clone_b)
        assert result['cache_deleted'] >= 1
        assert ws.server_cache_files() == []

    def test_re_declaring_after_rm_works(self, ws, capsys):
        self._declared_and_pushed(ws, capsys)
        CLI__Cache().cmd_cache_rm(_Args(path='keys/api.json', directory=ws.origin))
        capsys.readouterr()
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)
        assert len(ws.server_cache_files()) == 1               # back, on purpose this time
        obj = ws.read_cache_from_server('keys/api.json')
        assert obj is not None


class Test_QA__S3__H__Stale_Clone_Cannot_Destroy_Caches:
    """A clone whose head is behind the server must not reconcile (review 08/14 #2):
    its stale flat map would classify other clients' fresh caches as orphans."""

    def test_stale_up_to_date_push_leaves_fresh_caches_alone(self, ws, capsys):
        ws.write(ws.origin, 'pages/home.md', '# Home v1\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)

        # B clones, adds a NEW file, declares a cache for it, pushes everything
        clone_b = ws.clone_into('clone_b')
        ws.write(clone_b, 'keys/new.json', '{"fresh":"from-B"}')
        ws.sync().commit(clone_b, 'B adds a key')
        ws.sync().push(clone_b)
        ws.declare(clone_b, 'keys/new.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(clone_b)
        assert len(ws.server_cache_files()) == 1

        # origin is now BEHIND (no pull) and has nothing to commit; its push used
        # to reconcile from the stale head and DELETE B's valid cache
        result = ws.sync().push(ws.origin)
        assert result['status'] == 'up_to_date'
        assert result.get('cache_deleted', 0) == 0
        assert len(ws.server_cache_files()) == 1, 'stale clone destroyed a fresh cache'
        obj = ws.read_cache_from_server('keys/new.json')
        assert base64.b64decode(str(obj.value_b64)) == b'{"fresh":"from-B"}'

    def test_stale_repair_refuses_to_run(self, ws, capsys):
        from sgit_ai.core.actions.cache.Vault__Cache_Repair import Vault__Cache_Repair
        ws.write(ws.origin, 'pages/home.md', '# Home v1\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        ws.write(clone_b, 'keys/new.json', '{"fresh":"from-B"}')
        ws.sync().commit(clone_b, 'B adds a key')
        ws.sync().push(clone_b)
        ws.declare(clone_b, 'keys/new.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(clone_b)

        repair = Vault__Cache_Repair(crypto=Vault__Crypto(), api=ws.api)
        result = repair.repair(ws.origin)                      # origin never pulled
        assert result['status'] == 'stale_head'
        assert len(ws.server_cache_files()) == 1               # untouched

        ws.sync().pull(ws.origin)
        result = repair.repair(ws.origin)                      # now allowed
        assert result['status'] == 'ok'
        assert len(ws.server_cache_files()) == 1


class Test_QA__S3__I__D4_Converges_Across_Clones:
    """Two clones declaring different kinds for one path must converge to ONE
    object on the next aware push, not be maintained side by side forever."""

    def test_cross_clone_duplicate_kinds_converge_on_push(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        ws.declare(clone_b, 'keys/api.json', Enum__Cache_Kind.POINTER, capsys)
        ws.sync().push(clone_b)

        files = ws.server_cache_files()
        assert len(files) == 1, f'D4 violated on the server: {files}'

        # and it STAYS converged on later pushes from either side
        ws.sync().push(ws.origin)
        assert len(ws.server_cache_files()) == 1

    def test_kind_replacement_sticks_across_pushes(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        # switch kind: the old kind's server copy must die and STAY dead
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.POINTER, capsys)
        ws.sync().push(ws.origin)
        files = ws.server_cache_files()
        assert files == [f'bare/cache/pointer/{ws.cache_id("keys/api.json", Enum__Cache_Kind.POINTER)}']

        ws.sync().push(ws.origin)                              # no resurrection either
        assert ws.server_cache_files() == files


class Test_QA__S3__J__One_Bad_Object_Never_Aborts:
    """Fail-soft must be per-object (review 08/14 #5): one broken cache cannot
    freeze the whole cache layer."""

    def _blob_id_of(self, ws, directory, path):
        _, _, flat, _, _, _ = CLI__Cache()._head(ws.sync(), directory)
        return flat[path]['blob_id']

    def test_missing_local_blob_is_fetched_from_the_server(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'docs/read.md',  '# Docs\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        blob_id = self._blob_id_of(ws, clone_b, 'keys/api.json')
        os.remove(os.path.join(clone_b, '.sg_vault', 'bare', 'data', blob_id))

        ws.write(clone_b, 'docs/read.md', '# Docs v2\n')       # unrelated edit
        ws.sync().commit(clone_b, 'B edits docs')
        result = ws.sync().push(clone_b)

        assert result['cache_updated'] >= 1                    # healed via server fetch
        obj = ws.read_cache_from_server('keys/api.json')
        assert base64.b64decode(str(obj.value_b64)) == b'{"k":"v1"}'

    def test_blob_missing_everywhere_skips_that_object_but_heals_the_rest(self, ws, capsys):
        # Exercised through `repair` (push pulls first, and the vault's own pull
        # integrity guard is — correctly — loud about a blob deleted server-side).
        from sgit_ai.core.actions.cache.Vault__Cache_Repair import Vault__Cache_Repair
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'pages/home.md', '# Home\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        # make one cache stale so repair has real work, then lose its blob everywhere
        stale = ws.manager.build_value(path='pages/home.md', content=b'OLD',
                                       commit_id='obj-cas-imm-000000000000',
                                       content_type='', content_hash='aabbccddeeff')
        home_cid = ws.cache_id('pages/home.md', Enum__Cache_Kind.VALUE)
        ws.manager.save(ws.origin, Enum__Cache_Kind.VALUE, home_cid, stale, ws.read_key)
        blob_id = self._blob_id_of(ws, ws.origin, 'keys/api.json')
        os.remove(os.path.join(ws.origin, '.sg_vault', 'bare', 'data', blob_id))
        ws.api.delete(ws.vault_id, f'bare/data/{blob_id}', 'x')   # gone everywhere

        result = Vault__Cache_Repair(crypto=Vault__Crypto(), api=ws.api).repair(ws.origin)
        assert result['status']   == 'ok'                      # no crash (used to traceback)
        assert result['skipped']  >= 1                         # the unhealable one
        assert result['repaired'] >= 1                         # the stale one still healed
        assert len(ws.server_cache_files()) == 2               # skipped ≠ deleted
        home = ws.read_cache_from_server('pages/home.md')
        assert base64.b64decode(str(home.value_b64)) == b'# Home\n'

    def test_value_grown_past_the_cap_is_dropped_not_fatal(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.write(ws.origin, 'pages/home.md', '# Home\n')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        ws.declare(ws.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        ws.sync().push(ws.origin)

        ws.write(ws.origin, 'keys/api.json', 'x' * (1024 * 1024 + 100))   # past 1 MB cap
        ws.write(ws.origin, 'pages/home.md', '# Home v2\n')
        ws.sync().commit(ws.origin, 'grow')
        result = ws.sync().push(ws.origin)

        assert result['cache_deleted'] >= 1                    # cannot fit a batch write
        assert result['cache_updated'] >= 1                    # the other one still healed
        assert ws.read_cache_from_server('keys/api.json') is None
        home = ws.read_cache_from_server('pages/home.md')
        assert base64.b64decode(str(home.value_b64)) == b'# Home v2\n'


class Test_QA__S3__K__Read_Only_And_Branch_Only:

    def test_read_only_clone_cannot_declare_caches(self, ws, capsys):
        import json as _json
        import pytest as _pytest
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)

        clone_b = ws.clone_into('clone_b')
        keys    = ws.crypto.derive_keys_from_vault_key(ws.vault_key)
        with open(os.path.join(clone_b, '.sg_vault', 'local', 'clone_mode.json'), 'w') as f:
            _json.dump({'mode': 'read-only', 'vault_id': ws.vault_id,
                        'read_key': keys['read_key_bytes'].hex()}, f)

        with _pytest.raises(SystemExit):
            CLI__Cache().cmd_cache_add(_Args(path='keys/api.json', directory=clone_b,
                                             pointer=False, value=True))
        assert 'read-only' in capsys.readouterr().err

    def test_branch_only_push_reports_skipped_caches(self, ws, capsys):
        ws.write(ws.origin, 'keys/api.json', '{"k":"v1"}')
        ws.sync().commit(ws.origin, 'initial')
        ws.sync().push(ws.origin)
        ws.declare(ws.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)

        ws.write(ws.origin, 'keys/api.json', '{"k":"v2"}')
        ws.sync().commit(ws.origin, 'edit')
        result = ws.sync().push(ws.origin, branch_only=True)
        assert result['status'] == 'pushed_branch_only'
        assert result.get('cache_skipped', 0) >= 1             # loudly not published
