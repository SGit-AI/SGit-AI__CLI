"""Deep review of the partial-clone / bulk-fetch PR (6 Oct 2026): each finding
that changed code has a test here that fails on the pre-review code.

Hardening (security sub-review):
  - a host answering a batch read with a file_id that was never requested is
    ignored (the id names the on-disk write path);
  - Vault__Verified_Write writes only bare-store leaves, never local/… or a
    protected dir;
  - the pull guard lets an untracked collision through only when the DECRYPTED
    incoming blob proves the content identical (never the tree entry's claim).
Correctness (code review): scoped tracked-wins, scoped read-only clones,
ls/fetch on a scoped clone, friendly error on a partial clone, bounded
branch-only push, widen never overwrites, bulk sweep fail-soft, status does
not walk local history, scope validation.
"""
import base64
import json
import os
import pytest

from tests._helpers.vault_test_env                 import Vault__Test_Env
from sgit_ai.core.Vault__Sync                      import Vault__Sync
from sgit_ai.core.Vault__Errors                    import Vault__Scoped_Clone_Error, Vault__Dirty_Working_Tree_Error
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory     import Vault__API__In_Memory
from sgit_ai.storage.Vault__Scope                  import Vault__Scope
from sgit_ai.storage.Vault__Verified_Write         import Vault__Verified_Write
from sgit_ai.core.actions.pull.Vault__Pull__Guard  import Vault__Pull__Guard

FILES = {'README.md': 'root', 'mail/crm/a.txt': 'a v1', 'mail/crm/sub/b.txt': 'b v1',
         'mail/inbox/c.txt': 'c v1', 'runs/r1.json': '{}', 'docs/d.md': 'd v1'}


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    mode = 'wb' if isinstance(content, bytes) else 'w'
    with open(full, mode) as f: f.write(content)

def _read(d, rel):
    with open(os.path.join(d, rel)) as f: return f.read()

def _tree(d):
    return sorted(os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs if '.sg_vault' not in r)


class _Counting_API(Vault__API__In_Memory):
    def setup(self):
        super().setup(); self.batch_calls = []; self.fail_on = None; return self
    def batch_read(self, vault_id, file_ids, failures=None):
        self.batch_calls.append(list(file_ids))
        if self.fail_on and any(self.fail_on in f for f in file_ids):
            self.fail_on = None                                      # once: the sweep's chunk; the walk's retry succeeds
            raise RuntimeError('API Error: HTTP 503 Service Unavailable')
        return super().batch_read(vault_id, file_ids, failures)
    def objects_requested(self):
        return sum(1 for call in self.batch_calls for f in call if '/bare/data/obj-' in f'/{f}')


class _Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files=FILES)

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        self.api   = _Counting_API(); self.api.setup(); self.api._store = self.env.api._store
        self.psync = Vault__Sync(crypto=self.env.crypto, api=self.api)

    def teardown_method(self):
        self.env.cleanup()

    def _alice_pushes(self, files, message='alice'):
        for rel, content in files.items(): _write(self.alice, rel, content)
        self.sync.commit(self.alice, message=message); self.sync.push(self.alice)

    def _clone(self, name, **kw):
        target = os.path.join(self.env.tmp_dir, name)
        return target, self.psync.clone(self.env.vault_key, target, **kw)


# ---------------------------------------------------------------- hardening

class Test_Verified_Write__Store_Paths_Only:

    def setup_method(self):
        self.crypto = Vault__Crypto(); self.w = Vault__Verified_Write(crypto=self.crypto)

    def test_only_bare_store_leaves_are_store_paths(self):
        oid = self.crypto.compute_object_id(b'x')
        for ok in (f'bare/data/{oid}', 'bare/refs/ref-pid-muw-abc', 'bare/indexes/idx-1', 'bare/keys/k1',
                   'bare/branches/b1', 'bare/pending/p1', 'bare/cache/value/cch-1', 'bare/cache/pointer/cch-2'):
            assert self.w.is_store_path(ok), ok
        for bad in ('local/config.json', 'local/vault_key', 'README.md', 'bare/data/a/b', 'bare/cache/x',
                    'bare/other/x', 'bare/data/', '/bare/data/x', 'bare/data/../local/config.json',
                    'bare/keys/.sg_vault', '', None):
            assert not self.w.is_store_path(bad), bad

    def test_save_refuses_a_host_file_id_outside_the_store(self, tmp_path):
        base = str(tmp_path)
        assert self.w.save(base, 'local/config.json', b'{"mode":"read_only"}') == self.w.REFUSED
        assert self.w.save(base, 'bare/keys/../local/vault_key', b'k') == self.w.REFUSED
        assert self.w.save(base, 'bare/data/.git/hooks', b'x') == self.w.REFUSED
        assert sorted(os.listdir(tmp_path)) == []

    def test_save_still_writes_a_verified_object_and_a_ref(self, tmp_path):
        data = b'ciphertext'; oid = self.crypto.compute_object_id(data)
        assert self.w.save(str(tmp_path), f'bare/data/{oid}', data) == self.w.VERIFIED
        assert self.w.save(str(tmp_path), 'bare/refs/ref-pid-muw-abc', b'{}') == self.w.VERIFIED
        assert (tmp_path / 'bare' / 'data' / oid).read_bytes() == data


class Test_Pull_Guard__Untracked_Collision_Proven_From_Blob:

    def setup_method(self):
        self.guard = Vault__Pull__Guard()

    def test_entry_hash_alone_no_longer_lets_an_overwrite_through(self):
        merged = {'n': {'blob_id': 'N1', 'content_hash': 'same'}}
        scan   = {'n': {'content_hash': 'same'}}
        plan   = self.guard.plan({'n': 'untracked'}, {}, merged, scan)              # no blob proof available
        assert [p for p, _ in plan['blocked']] == ['n']
        plan   = self.guard.plan({'n': 'untracked'}, {}, merged, scan, blob_hash_fn=lambda b: 'other')
        assert [p for p, _ in plan['blocked']] == ['n']                                # the entry lied

    def test_blob_proof_lets_identical_content_through(self):
        merged = {'n': {'blob_id': 'N1', 'content_hash': 'whatever-the-commit-claims'}}
        scan   = {'n': {'content_hash': 'same'}}
        plan   = self.guard.plan({'n': 'untracked'}, {}, merged, scan, blob_hash_fn=lambda b: 'same' if b == 'N1' else '')
        assert plan == {'carry_over': [], 'blocked': []}


class Test_Pull__Untracked_Collision__End_To_End(_Base):

    def test_identical_untracked_file_passes_on_the_real_blob(self):
        self._alice_pushes({'new.txt': 'same bytes'})
        _write(self.bob, 'new.txt', 'same bytes')
        assert self.sync.pull(self.bob)['status'] == 'merged'
        assert _read(self.bob, 'new.txt') == 'same bytes'

    def test_commit_whose_entry_hash_lies_cannot_overwrite_an_untracked_file(self):
        """Alice's commit claims the content hash of bob's local file but carries
        different bytes. The pre-review guard trusted the claim and overwrote."""
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        local = 'bob wrote this first'
        _write(self.bob, 'new.txt', local)
        lying_hash = self.env.crypto.content_hash(local.encode())
        original   = Vault__Sub_Tree.build_from_flat

        def build_with_a_lie(sub_tree, flat, read_key, **kw):
            if 'new.txt' in flat:
                flat['new.txt'] = dict(flat['new.txt'], content_hash=lying_hash)
            return original(sub_tree, flat, read_key, **kw)

        Vault__Sub_Tree.build_from_flat = build_with_a_lie
        try:
            self._alice_pushes({'new.txt': 'alice bytes'})
        finally:
            Vault__Sub_Tree.build_from_flat = original
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='new.txt'):
            self.sync.pull(self.bob)
        assert _read(self.bob, 'new.txt') == local


# ---------------------------------------------------------------- code review

class Test_Scoped_Clone__Readers(_Base):

    def test_tracked_ignored_file_survives_status_and_commit_on_a_scoped_clone(self):
        # a file under an always-ignored dir tracked by the vault (legacy state) must stay tracked
        self.sync.write_file(self.alice, 'mail/crm/.github/x.yml', b'name: ci\n', message='legacy'); self.sync.push(self.alice)
        d, _ = self._clone('tw', scope_paths=['mail/crm'])
        assert self.sync.status(d)['clean'] is True
        _write(d, 'mail/crm/a.txt', 'a v2'); self.psync.commit(d, message='edit'); self.psync.push(d)
        self.sync.pull(self.alice)
        assert os.path.isfile(os.path.join(self.alice, 'mail/crm/.github/x.yml'))
        assert _read(self.alice, 'mail/crm/a.txt') == 'a v2'

    def test_read_only_scoped_clone_status_and_pull(self):
        keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        d    = os.path.join(self.env.tmp_dir, 'ro')
        self.psync.clone_read_only(keys['vault_id'], keys['read_key'], d, scope_paths=['docs'])
        assert self.psync.status(d)['clean'] is True
        self._alice_pushes({'docs/d.md': 'd v2', 'README.md': 'root v2'})
        self.psync.pull_read_only(d)
        assert _read(d, 'docs/d.md') == 'd v2' and _tree(d) == ['docs/d.md']

    def test_ls_and_fetch_on_a_scoped_clone_see_only_the_held_folders(self):
        d, _ = self._clone('ls', scope_paths=['mail/crm'])
        paths = sorted(e['path'] for e in self.psync.sparse_ls(d))
        assert paths == ['mail/crm/a.txt', 'mail/crm/sub/b.txt']
        assert self.psync.sparse_fetch(d, 'mail/crm')['already_local'] == 2
        assert self.psync.sparse_cat(d, 'mail/crm/a.txt') == b'a v1'

    def test_friendly_error_for_a_missing_object_names_the_scope(self, capsys):
        d, _ = self._clone('err', scope_paths=['mail/crm'])
        from sgit_ai.cli.CLI__Main import CLI__Main
        import types
        CLI__Main()._print_friendly_error(FileNotFoundError('obj-cas-imm-000000000000'),
                                          types.SimpleNamespace(command='check fsck', directory=d))
        err = capsys.readouterr().err
        assert 'holds only part of the vault' in err and 'mail/crm' in err and 'sgit fetch' in err
        assert 'corrupted' not in err

    def test_scope_validation_rejects_traversal_and_bad_boundaries(self):
        for bad in ('../x', '/etc', 'a/../../b', 'C:\\x'):
            with pytest.raises(ValueError):
                Vault__Scope().with_paths([bad])
        with pytest.raises(ValueError):
            Vault__Scope().with_boundaries(['not-an-object-id'])
        assert Vault__Scope().with_paths(['mail/crm/', './docs']).paths == ['mail/crm', 'docs']
        assert Vault__Scope().with_paths(['mail/crm', 'mail', 'docs']).paths == ['mail', 'docs']   # nested collapses

    def test_scope_hands_consumers_plain_strings(self):
        """The typed fields validate; what the store walks must be plain str. A
        Safe_Str hashes differently from the same str (set membership fails) and
        os.path.join sanitises it ('/' -> '_'): with the typed values used
        directly, unshallow found no boundary commit and status walked past it."""
        cid   = 'obj-cas-imm-4c92b0408831'
        scope = Vault__Scope().with_paths(['mail/crm']).with_boundaries([cid])
        assert type(scope.boundaries[0]) is not str                      # validated on the way in
        assert [type(b) for b in scope.boundary_ids()] == [str] and scope.boundary_ids() == [cid]
        assert [type(f) for f in scope.folders()] == [str]
        assert cid in set(scope.boundary_ids()) and scope.is_boundary(cid)
        assert os.path.join('/x', scope.boundary_ids()[0]) == f'/x/{cid}'


class Test_Widen__Never_Overwrites(_Base):

    def test_widen_refuses_when_a_file_on_disk_differs(self):
        d, _ = self._clone('wd', scope_paths=['mail/crm'])
        _write(d, 'docs/d.md', 'my local notes')
        with pytest.raises(Vault__Scoped_Clone_Error, match='docs/d.md'):
            self.psync.widen(d, 'docs')
        assert _read(d, 'docs/d.md') == 'my local notes'
        assert self.sync.scope_of(d).paths == ['mail/crm']                 # config untouched
        os.remove(os.path.join(d, 'docs/d.md'))
        assert self.psync.widen(d, 'docs')['written'] == 1

    def test_widen_to_a_parent_keeps_held_files_and_collapses_the_scope(self):
        d, _ = self._clone('wp', scope_paths=['mail/crm'])
        _write(d, 'mail/crm/a.txt', 'edited, uncommitted')
        out = self.psync.widen(d, 'mail')
        assert out['already_held'] is False and _read(d, 'mail/inbox/c.txt') == 'c v1'
        assert _read(d, 'mail/crm/a.txt') == 'edited, uncommitted'         # held files are never rewritten
        assert self.sync.scope_of(d).paths == ['mail']


class Test_Branch_Only_Push__Bounded(_Base):

    def _written_by(self, push):
        """The bare/data ids a push wrote, by watching the in-memory batch endpoint."""
        written = []; original = self.env.api.batch
        def spy(vault_id, write_key, operations):
            written.extend(op['file_id'] for op in operations if op.get('op') != 'read')
            return original(vault_id, write_key, operations)
        self.env.api.batch = spy
        try:
            return push(), written
        finally:
            self.env.api.batch = original

    def test_second_branch_only_push_uploads_only_the_new_objects(self):
        _write(self.bob, 'w1.txt', 'one'); self.sync.commit(self.bob, message='w1')
        first, _ = self._written_by(lambda: self.sync.push(self.bob, branch_only=True))
        assert first['status'] == 'pushed_branch_only' and first['commits_pushed'] == 1
        _write(self.bob, 'w2.txt', 'two'); self.sync.commit(self.bob, message='w2')
        before = set(self.env.api._store)
        second, written = self._written_by(lambda: self.sync.push(self.bob, branch_only=True))
        assert second['commits_pushed'] == 1
        c = self.sync._init_components(self.bob)
        vid = str(c.vault_id)
        # the server's clone ref now points at w2 (the CAS matched the server's bytes, not the local file's)
        assert json.loads(self.env.crypto.decrypt(c.read_key, self.env.api.read(vid, f"bare/refs/{second['branch_ref_id']}")))['commit_id'] == second['commit_id']
        # anything re-sent that the server already had is a tree (siblings of the changed root), never a blob
        resent = [f for f in written if f.startswith('bare/data/') and f'{vid}/{f}' in before]
        for fid in resent:
            plain = self.env.crypto.decrypt(c.read_key, c.obj_store.load(fid.rsplit('/', 1)[-1]))
            assert b'"entries"' in plain, f'{fid} re-uploaded but is not a tree'
        new = [f for f in written if f.startswith('bare/data/') and f'{vid}/{f}' not in before]
        assert len(new) == 3                                             # w2's blob, the new root tree, the commit

    def test_branch_only_push_from_a_scoped_clone_does_not_need_unheld_blobs(self):
        d, _ = self._clone('bo', scope_paths=['mail/crm'])
        _write(d, 'mail/crm/a.txt', 'branch only'); self.psync.commit(d, message='bo')
        r = self.psync.push(d, branch_only=True)
        assert r['status'] == 'pushed_branch_only'


class Test_Bulk_Sweep__Fail_Soft(_Base):

    def test_a_failing_chunk_does_not_abort_the_clone(self, monkeypatch):
        import sgit_ai.workflow.clone.Step__Clone__Bulk_Fetch as bulk
        monkeypatch.setattr(bulk, 'BULK_CHUNK', 2)
        some_blob = next(k.rsplit('/', 1)[-1] for k in self.env.api._store if '/bare/data/obj-cas-imm-' in k)
        self.api.fail_on = some_blob
        d, r = self._clone('fs')
        assert self.api.fail_on is None                                # the sweep did hit the failure
        assert _tree(d) == sorted(FILES)                               # the walks fetched what the sweep missed
        assert self.sync.status(d)['clean'] is True


class Test_Status__Does_Not_Walk_Local_History(_Base):

    def _bob_history(self, n=3):
        for i in range(n):
            _write(self.bob, 'x.txt', f'v{i}'); self.sync.commit(self.bob, message=f'c{i}'); self.sync.push(self.bob)

    def test_status_on_an_up_to_date_clone_reads_no_objects(self):
        self._bob_history(); self.sync.pull(self.alice)
        api = _Counting_API(); api.setup(); api._store = self.env.api._store
        st  = Vault__Sync(crypto=self.env.crypto, api=api).status(self.alice)
        assert (st['ahead'], st['behind']) == (0, 0)
        assert api.objects_requested() == 0

    def test_status_n_behind_fetches_exactly_n_commits(self):
        self._bob_history()
        api = _Counting_API(); api.setup(); api._store = self.env.api._store
        st  = Vault__Sync(crypto=self.env.crypto, api=api).status(self.alice)
        assert (st['ahead'], st['behind']) == (0, 3)
        assert api.objects_requested() == 3


class Test_API__Ignores_Unrequested_File_Ids:

    def test_batch_read_drops_results_the_host_was_not_asked_for(self, monkeypatch):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from sgit_ai.network.api.Vault__API import Vault__API

        class _H(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *a): pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                fids = [op['file_id'] for op in json.loads(body)['operations']]
                results = [{'file_id': f, 'status': 'ok', 'data': base64.b64encode(b'ok').decode()} for f in fids]
                results.append({'file_id': 'local/config.json', 'status': 'ok',
                                'data': base64.b64encode(b'{"mode":"read_only"}').decode()})
                results.append({'file_id': 'bare/data/obj-cas-imm-evil00000000', 'status': 'ok',
                                'data': base64.b64encode(b'evil').decode()})
                data = json.dumps({'results': results}).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

        for var in ('HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy'):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), _H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            api = Vault__API(base_url=f'http://127.0.0.1:{httpd.server_address[1]}', access_token='t').setup()
            out = api.batch_read('v1', ['bare/data/a', 'bare/data/b'])
            api.close()
        finally:
            httpd.shutdown(); httpd.server_close()
        assert out == {'bare/data/a': b'ok', 'bare/data/b': b'ok'}
