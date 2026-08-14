"""Vault__Cache_Reader — the one-request read fast path (contract §7).

The properties under test are the ones the contract makes normative: one round
trip on a fresh hit, the path-mismatch collision guard, staleness detection via
commit_id, and — most importantly — that every failure mode returns
fallback=True rather than a wrong answer.
"""
import base64
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.cache.Vault__Cache_Reader import Vault__Cache_Reader
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.storage.Vault__Storage                 import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager           import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind            import Enum__Cache_Kind


class _Base:

    def setup_method(self):
        self.tmp     = tempfile.mkdtemp()
        self.vault   = os.path.join(self.tmp, 'vault')
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory().setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.storage = Vault__Storage()
        self.manager = Vault__Cache_Manager(crypto=self.crypto, storage=self.storage)
        self.reader  = Vault__Cache_Reader(crypto=self.crypto, api=self.api)

        init          = self.sync.init(self.vault)
        self.vault_id = init['vault_id']
        self.rk       = self.crypto.derive_keys_from_vault_key(init['vault_key'])['read_key_bytes']

        self._write('pages/home.md', '# Home\n')
        self._write('media/a.txt',   'photo')
        self.sync.commit(self.vault, 'initial')
        self.sync.push(self.vault)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, text):
        p = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def _declare(self, path, kind=Enum__Cache_Kind.VALUE):
        from sgit_ai.cli.CLI__Cache import CLI__Cache
        class A:
            def __init__(s, **k): s.__dict__.update(k)
        CLI__Cache().cmd_cache_add(A(path=path, directory=self.vault,
                                     pointer=(kind == Enum__Cache_Kind.POINTER),
                                     value=(kind == Enum__Cache_Kind.VALUE)))
        self.sync.push(self.vault)                    # publish it


class Test_Cache_Reader__Fresh_Hit(_Base):

    def test_value_read_in_one_round_trip(self, capsys):
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        r = self.reader.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['found']       is True
        assert r['fresh']       is True
        assert r['fallback']    is False
        assert r['source']      == 'cache-value'
        assert r['content']     == b'# Home\n'
        assert r['round_trips'] == 1                  # the whole point

    def test_pointer_read_resolves_blob_in_two(self, capsys):
        self._declare('media/a.txt', Enum__Cache_Kind.POINTER)
        capsys.readouterr()
        r = self.reader.read_path(self.vault_id, self.rk, 'media/a.txt')
        assert r['source']      == 'cache-pointer'
        assert r['target_kind'] == 'blob'
        assert r['content']     == b'photo'
        assert r['round_trips'] == 2                  # locator + object

    def test_folder_pointer_returns_tree_id_without_resolving(self, capsys):
        self._declare('media', Enum__Cache_Kind.POINTER)
        capsys.readouterr()
        r = self.reader.read_path(self.vault_id, self.rk, 'media')
        assert r['target_kind'] == 'tree'
        assert str(r['target_id']).startswith('obj-cas-imm-')
        assert r['round_trips'] == 1                  # a tree is a walk start, not content

    def test_works_from_read_key_alone__no_clone(self, capsys):
        # The §4.2 capability: a Lambda holding only vault_id + read_key.
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        detached = Vault__Cache_Reader(crypto=Vault__Crypto(), api=self.api)
        r = detached.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['fresh'] is True and r['content'] == b'# Home\n'


class Test_Cache_Reader__Fallback_Paths(_Base):
    """Every failure mode must say 'fall back', never return a wrong answer."""

    def test_undeclared_path_is_a_miss(self):
        r = self.reader.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['found']    is False
        assert r['fallback'] is True
        assert r['content']  is None

    def test_stale_cache_is_detected_and_flagged(self, capsys):
        # The reader compares against the SERVER ref (contract §7), so staleness is
        # simulated by publishing an object whose commit_id lags the published head.
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        cid   = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md',
                                      Enum__Cache_Kind.VALUE)
        stale = self.manager.build_value(path='pages/home.md', content=b'OLD',
                                         commit_id='obj-cas-imm-000000000000',
                                         content_type='text/markdown', content_hash='aabbccddeeff')
        self.api.write(self.vault_id, self.manager.file_id(Enum__Cache_Kind.VALUE, cid),
                       'x', self.manager.encrypt_object(stale, self.rk))

        r = self.reader.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['found']    is True
        assert r['fresh']    is False                 # commit_id lags the ref
        assert r['fallback'] is True                  # caller must walk for strong freshness

    def test_path_mismatch_is_rejected(self, capsys):
        # simulate a 48-bit id collision: an object whose recorded path differs
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        cid = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.VALUE)
        bogus = self.manager.build_value(path='some/other/file.md', content=b'WRONG',
                                         commit_id='obj-cas-imm-aaaaaaaaaaaa',
                                         content_type='text/markdown', content_hash='aabbccddeeff')
        self.manager.save(self.vault, Enum__Cache_Kind.VALUE, cid, bogus, self.rk)
        self.api.write(self.vault_id, self.manager.file_id(Enum__Cache_Kind.VALUE, cid),
                       'x', self.manager.encrypt_object(bogus, self.rk))

        r = self.reader.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['found']    is False                 # guard rejected it
        assert r['content']  is None
        assert r['fallback'] is True

    def test_unknown_vault_does_not_raise(self):
        r = self.reader.read_path('zzzznope', self.rk, 'pages/home.md')
        assert r['found'] is False and r['fallback'] is True


class Test_Cache_Reader__Candidates(_Base):

    def test_probes_both_mutability_labels(self):
        cands = self.reader.candidate_ids(self.rk, self.vault_id, 'a.txt', Enum__Cache_Kind.VALUE)
        ids   = [c[1] for c in cands]
        assert any(i.startswith('cch-pid-snw-') for i in ids)
        assert any(i.startswith('cch-pid-muw-') for i in ids)
        assert len({i.rsplit('-', 1)[1] for i in ids}) == 1     # same hash tail

    def test_probes_both_kinds_when_unspecified(self):
        cands = self.reader.candidate_ids(self.rk, self.vault_id, 'a.txt')
        assert {c[0] for c in cands} == {Enum__Cache_Kind.VALUE, Enum__Cache_Kind.POINTER}
        assert len(cands) == 4                                   # 2 kinds x 2 labels, one batch


class Test_Cache_Reader__Degraded_Objects(_Base):
    """Review 08/14 H3/M1/L2 — the 'never raises, never lies' edge cases."""

    def test_pointer_blob_read_failure_forces_fallback(self, capsys, monkeypatch):
        # A fresh pointer whose +1 blob read fails must NOT return fallback=False
        # with content=None — a contract-following caller would serve nothing.
        self._declare('media/a.txt', Enum__Cache_Kind.POINTER)
        capsys.readouterr()

        def _broken_read(api_self, vault_id, file_id):
            raise RuntimeError('transient 5xx')
        monkeypatch.setattr(type(self.api), 'read', _broken_read)

        r = self.reader.read_path(self.vault_id, self.rk, 'media/a.txt')
        assert r['found']    is True
        assert r['fresh']    is True
        assert r['content']  is None
        assert r['fallback'] is True                  # the fix: caller must tree-walk

    def test_malformed_base64_is_a_miss_not_an_exception(self, capsys):
        # A mirror client emitting unpadded base64 passes the Safe type but
        # cannot be decoded — the reader must degrade, not raise (M1).
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        cid = self.manager.cache_id(self.rk, self.vault_id, 'pages/home.md',
                                    Enum__Cache_Kind.VALUE)
        obj = self.manager.load(self.vault, Enum__Cache_Kind.VALUE, cid, self.rk)
        obj.value_b64 = 'aGk'                          # valid per Safe type, unpadded
        self.api.write(self.vault_id, self.manager.file_id(Enum__Cache_Kind.VALUE, cid),
                       'x', self.manager.encrypt_object(obj, self.rk))

        r = self.reader.read_path(self.vault_id, self.rk, 'pages/home.md')
        assert r['found']    is False                  # skipped, no crash
        assert r['fallback'] is True

    def test_fresh_pointer_wins_over_stale_value(self, capsys):
        # D4 violated on the server: a stale VALUE must not shadow the fresh
        # POINTER the same batch already fetched (L2).
        self._declare('media/a.txt', Enum__Cache_Kind.POINTER)
        capsys.readouterr()
        vid   = self.manager.cache_id(self.rk, self.vault_id, 'media/a.txt',
                                      Enum__Cache_Kind.VALUE)
        stale = self.manager.build_value(path='media/a.txt', content=b'OLD',
                                         commit_id='obj-cas-imm-000000000000',
                                         content_type='', content_hash='aabbccddeeff')
        self.api.write(self.vault_id, self.manager.file_id(Enum__Cache_Kind.VALUE, vid),
                       'x', self.manager.encrypt_object(stale, self.rk))

        r = self.reader.read_path(self.vault_id, self.rk, 'media/a.txt')
        assert r['source']   == 'cache-pointer'        # the fresh one
        assert r['fresh']    is True
        assert r['content']  == b'photo'
        assert r['fallback'] is False


class Test_Cat_Fast_Path(_Base):
    """`sgit cat` uses the cache when fresh, and is transparent otherwise."""

    def test_cat_returns_cached_content(self, capsys):
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        assert self.sync.sparse_cat(self.vault, 'pages/home.md') == b'# Home\n'

    def test_cat_correct_after_edit_even_though_cache_is_stale(self, capsys):
        self._declare('pages/home.md', Enum__Cache_Kind.VALUE)
        capsys.readouterr()
        self._write('pages/home.md', '# Home v2\n')
        self.sync.commit(self.vault, 'edit')          # cache now stale
        # must return the HEAD content, not the stale cached copy
        assert self.sync.sparse_cat(self.vault, 'pages/home.md') == b'# Home v2\n'

    def test_cat_works_without_any_cache(self):
        assert self.sync.sparse_cat(self.vault, 'media/a.txt') == b'photo'
