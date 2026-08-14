"""Integration tests for the cache layer against the real SG/Send test server.

The QA scenario proves the multi-clone logic against the in-memory API. These
run the same workflow over real HTTP, so they also exercise what only a real
server can: the batch endpoint's handling of nested `bare/cache/...` file_ids,
prefix listing, deletes, and the one-request read path over the wire.

Uses the shared `vault_api` fixture (local SG/Send test server, in-memory
storage). No env vars, no live API.
"""
import base64
import os
import secrets
import string

import pytest

from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.cache.Vault__Cache_Reader import Vault__Cache_Reader
from sgit_ai.core.actions.cache.Vault__Cache_Repair import Vault__Cache_Repair
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.storage.Vault__Storage                 import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager           import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind            import Enum__Cache_Kind
from sgit_ai.cli.CLI__Cache                         import CLI__Cache


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _rand_id():
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))


class _Env:
    """Origin vault plus clones, all on a real server."""

    def __init__(self, vault_api, tmp):
        self.api       = vault_api
        self.tmp       = tmp
        self.crypto    = Vault__Crypto()
        self.storage   = Vault__Storage()
        self.manager   = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)
        self.vault_key = f'cacheintegpass01:{_rand_id()}'
        self.origin    = os.path.join(tmp, 'origin')
        self.sync().init(self.origin, vault_key=self.vault_key)
        keys           = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.vault_id  = keys['vault_id']
        self.read_key  = keys['read_key_bytes']

    def sync(self):
        return Vault__Sync(crypto=Vault__Crypto(), api=self.api)

    def write(self, vault_dir, rel, text):
        p = os.path.join(vault_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def read(self, vault_dir, rel):
        with open(os.path.join(vault_dir, rel)) as f:
            return f.read()

    def declare(self, vault_dir, path, kind=Enum__Cache_Kind.VALUE, capsys=None):
        CLI__Cache().cmd_cache_add(_Args(path=path, directory=vault_dir,
                                         pointer=(kind == Enum__Cache_Kind.POINTER),
                                         value=(kind == Enum__Cache_Kind.VALUE)))
        if capsys:
            capsys.readouterr()

    def server_cache_files(self):
        return [str(f) for f in (self.api.list_files(self.vault_id, 'bare/cache/') or [])]


@pytest.fixture()
def env(vault_api, temp_dir):
    return _Env(vault_api, temp_dir)


class Test_Cache__Integration__Publish_And_Read:

    def test_declared_cache_reaches_the_real_server(self, env, capsys):
        env.write(env.origin, 'pages/home.md', '# Home\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        files = env.server_cache_files()
        assert len(files) == 1
        assert files[0].startswith('bare/cache/value/cch-pid-')   # nested file_id survived

    def test_one_request_read_over_http(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"hot"}')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=env.api)
        result = reader.read_path(env.vault_id, env.read_key, 'keys/api.json')
        assert result['fresh']       is True
        assert result['content']     == b'{"k":"hot"}'
        assert result['round_trips'] == 1

    def test_folder_pointer_over_http(self, env, capsys):
        env.write(env.origin, 'media/a.txt', 'photo-a')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'media', Enum__Cache_Kind.POINTER, capsys)
        env.sync().push(env.origin)

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=env.api)
        result = reader.read_path(env.vault_id, env.read_key, 'media')
        assert result['target_kind'] == 'tree'
        assert str(result['target_id']).startswith('obj-cas-imm-')


class Test_Cache__Integration__Cross_Clone:

    def test_clone_pull_push_round_trip_with_caches(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"v1"}')
        env.write(env.origin, 'docs/read.md',  '# Docs\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        clone_b = os.path.join(env.tmp, 'clone_b')
        env.sync().clone(env.vault_key, clone_b)
        assert env.read(clone_b, 'keys/api.json') == '{"k":"v1"}'

        # B edits the cached record and pushes — must heal a cache it never declared
        env.write(clone_b, 'keys/api.json', '{"k":"v2-from-B"}')
        env.sync().commit(clone_b, 'B updates')
        result = env.sync().push(clone_b)
        assert result['cache_updated'] >= 1

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=env.api)
        got    = reader.read_path(env.vault_id, env.read_key, 'keys/api.json')
        assert got['fresh']   is True
        assert got['content'] == b'{"k":"v2-from-B"}'

        # origin pulls and agrees
        env.sync().pull(env.origin)
        assert env.read(env.origin, 'keys/api.json') == '{"k":"v2-from-B"}'

    def test_delete_propagates_to_the_server(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"v1"}')
        env.write(env.origin, 'docs/read.md',  '# Docs\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)
        assert len(env.server_cache_files()) == 1

        clone_b = os.path.join(env.tmp, 'clone_b')
        env.sync().clone(env.vault_key, clone_b)
        os.remove(os.path.join(clone_b, 'keys/api.json'))
        env.sync().commit(clone_b, 'B deletes', allow_deletions=True)
        result = env.sync().push(clone_b)

        assert result['cache_deleted'] >= 1
        assert env.server_cache_files() == []           # DELETE op reached the server


class Test_Cache__Integration__Repair:

    def test_repair_heals_drift_over_http(self, env, capsys):
        env.write(env.origin, 'pages/home.md', '# Home\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'pages/home.md', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        # corrupt the local object, then repair
        cid  = env.manager.cache_id(env.read_key, env.vault_id, 'pages/home.md',
                                    Enum__Cache_Kind.VALUE)
        stale = env.manager.build_value(path='pages/home.md', content=b'STALE',
                                        commit_id='obj-cas-imm-000000000000',
                                        content_type='text/markdown',
                                        content_hash='aabbccddeeff')
        env.manager.save(env.origin, Enum__Cache_Kind.VALUE, cid, stale, env.read_key)

        repair = Vault__Cache_Repair(crypto=Vault__Crypto(), api=env.api)
        result = repair.repair(env.origin)
        assert result['repaired'] >= 1

        reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=env.api)
        got    = reader.read_path(env.vault_id, env.read_key, 'pages/home.md')
        assert got['content'] == b'# Home\n'

    def test_orphan_removed_over_http(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"v1"}')
        env.write(env.origin, 'docs/read.md',  '# Docs\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        os.remove(os.path.join(env.origin, 'keys/api.json'))
        env.sync().commit(env.origin, 'drop the key', allow_deletions=True)

        repair = Vault__Cache_Repair(crypto=Vault__Crypto(), api=env.api)
        result = repair.repair(env.origin)
        assert result['deleted'] >= 1
        assert env.server_cache_files() == []


class Test_Cache__Integration__Correctness_Floor:

    def test_reads_stay_correct_with_every_cache_destroyed(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"v1"}')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)

        clone_b = os.path.join(env.tmp, 'clone_b')
        env.sync().clone(env.vault_key, clone_b)

        keys = env.crypto.derive_keys_from_vault_key(env.vault_key)
        for kind, cid in list(env.manager.list_all(env.origin)):
            env.manager.delete(env.origin, kind, cid)
            env.api.delete(env.vault_id, env.manager.file_id(kind, cid), keys['write_key'])

        assert env.sync().sparse_cat(env.origin, 'keys/api.json') == b'{"k":"v1"}'
        assert env.sync().sparse_cat(clone_b,    'keys/api.json') == b'{"k":"v1"}'


class Test_Cache__Integration__Rm_Lifecycle:
    """`cache rm` over real HTTP — the tombstone-driven DELETE of a nested
    file_id, and proof the D6 listing does not resurrect it afterwards."""

    def test_rm_deletes_on_server_and_stays_deleted(self, env, capsys):
        env.write(env.origin, 'keys/api.json', '{"k":"v1"}')
        env.write(env.origin, 'docs/read.md',  '# Docs\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)
        env.declare(env.origin, 'keys/api.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(env.origin)
        assert len(env.server_cache_files()) == 1

        CLI__Cache().cmd_cache_rm(_Args(path='keys/api.json', directory=env.origin))
        capsys.readouterr()
        result = env.sync().push(env.origin)
        assert result['cache_deleted'] >= 1
        assert env.server_cache_files() == []
        assert env.manager.tombstoned_ids(env.origin) == set()

        # a commit-carrying push afterwards must not resurrect it (the D6 union
        # used to re-fetch the server copy; now there is no server copy and no
        # local mirror, so the id is simply gone)
        env.write(env.origin, 'docs/read.md', '# Docs v2\n')
        env.sync().commit(env.origin, 'edit docs')
        result = env.sync().push(env.origin)
        assert result.get('cache_updated', 0) == 0
        assert env.server_cache_files() == []

    def test_stale_clone_up_to_date_push_cannot_destroy_fresh_caches(self, env, capsys):
        env.write(env.origin, 'pages/home.md', '# Home v1\n')
        env.sync().commit(env.origin, 'initial')
        env.sync().push(env.origin)

        clone_b = os.path.join(env.tmp, 'clone_b')
        env.sync().clone(env.vault_key, clone_b)
        env.write(clone_b, 'keys/new.json', '{"fresh":"from-B"}')
        env.sync().commit(clone_b, 'B adds a key')
        env.sync().push(clone_b)
        env.declare(clone_b, 'keys/new.json', Enum__Cache_Kind.VALUE, capsys)
        env.sync().push(clone_b)
        assert len(env.server_cache_files()) == 1

        result = env.sync().push(env.origin)          # origin is behind, no commits
        assert result['status'] == 'up_to_date'
        assert result.get('cache_deleted', 0) == 0
        assert len(env.server_cache_files()) == 1     # B's cache survived
