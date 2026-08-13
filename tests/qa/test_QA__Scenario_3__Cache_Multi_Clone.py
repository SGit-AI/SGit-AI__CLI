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
