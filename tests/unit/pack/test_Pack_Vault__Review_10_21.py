"""One test per finding of the 21 Oct verification review (cli.sgit.ai's build agent,
`07fb24ba-pack-mode-verification.md`): each reproduces the reported behaviour on the
code before the fix and passes on the code after it."""
import io
import json
import os
import time
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs        import Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE, PACK_ORPHAN_AGE_S
from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
from sgit_ai.core.actions.tag.Vault__Sync__Tag     import Vault__Sync__Tag
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API                import Vault__API
from tests._helpers.pack_env                       import Pack__Env, Host__Counting
from tests._helpers.vault_test_env                 import TEST_VAULT_KEY, TEST_VAULT_KEYS


def _vid(sync, d):
    return sync._init_components(d).vault_id


class Test_Review_1__Compaction_Keeps_Other_Refs_History:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(2), vault_key=TEST_VAULT_KEY)
        self.vid = _vid(self.sync, self.a)
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        self.env.write(self.b, {'wip.md': b'work in progress\n'}); self.sync_b.commit(self.b, message='wip')
        self.sync_b.push(self.b, branch_only=True)                            # a ref on the host, not the named branch
        self.wip_pack = self.env.api.packs(self.vid, PACK_COMMITS)[0]

    def _age(self, name, days):
        old = Vault__Packs().parse_name(name.split('/')[-1])
        aged = Vault__Packs().pack_name(old['commit_id'], old['size'], epoch_s=int(time.time()) - days * 86400)
        self.env.api._store[f'{self.vid}/{PACK_COMMITS}{aged}'] = self.env.api._store.pop(f'{self.vid}/{name}')
        return PACK_COMMITS + aged

    def test_a_branch_only_pack_two_days_old_is_kept_not_archived(self):
        aged = self._age(self.wip_pack, 2)
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)
        plan  = maint.compact(self.a, dry_run=True)['plan']
        assert [e['file_id'] for e in plan['kept']] == [aged] and plan['orphans'] == []
        maint.compact(self.a)
        assert aged in self.env.api.packs(self.vid, PACK_COMMITS)              # still where a clone reads it
        sync_c, c = self.env.clone(self.key, 'c')
        assert os.path.isfile(os.path.join(c, '.sg_vault', 'bare', 'data', Vault__Packs().parse_name(aged.split('/')[-1])['commit_id']))

    def test_a_pack_no_ref_reaches_is_archived_once_old(self):
        packs = Vault__Packs(crypto=self.sync_b.crypto, api=self.env.api)
        c     = self.sync_b._init_components(self.b)
        self.env.write(self.b, {'gone.md': b'abandoned\n'}); gone = self.sync_b.commit(self.b, message='gone')['commit_id']
        path, _ = packs.build_commit_pack(os.path.join(self.b, '.sg_vault'), gone, c.read_key, os.path.join(self.env.root, 'w'))
        with open(path, 'rb') as f:
            data = f.read()
        name = packs.pack_name(gone, len(data), epoch_s=int(time.time()) - PACK_ORPHAN_AGE_S - 10)
        self.env.api._store[f'{self.vid}/{PACK_COMMITS}{name}'] = data       # pushed, then the branch was reset: no ref
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)
        plan  = maint.compact(self.a, dry_run=True)['plan']
        assert [e['name'] for e in plan['orphans']] == [name]

    def test_an_unreadable_or_unknown_ref_suspends_orphan_archiving(self):
        self.env.api._store[f'{self.vid}/bare/refs/ref-pid-snw-ffffffffffff'] = b'garbage the clone cannot read'
        aged  = self._age(self.wip_pack, 2)
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)
        plan  = maint.compact(self.a, dry_run=True)['plan']
        assert plan['unjudged'] and plan['orphans'] == [] and [e['file_id'] for e in plan['kept']] == [aged]


class Test_Review_2__Concurrent_Compaction:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(2), vault_key=TEST_VAULT_KEY)
        self.vid = _vid(self.sync, self.a)
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        self.env.write(self.b, {'b.md': b'b\n'}); self.sync_b.commit(self.b, message='b'); self.sync_b.push(self.b)
        self.sync.pull(self.a)

    def test_a_compaction_that_finds_the_branch_moved_archives_nothing(self):
        env, sync_b, b = self.env, self.sync_b, self.b

        class Maintain__Raced(Vault__Pack_Maintain):
            def _moves_about_to_start(self, c):                               # between X's snapshot and X's moves:
                env.write(b, {'c.md': b'c\n'}); sync_b.commit(b, message='c'); sync_b.push(b)   # Y pushes c6 ...
                Vault__Pack_Maintain(crypto=Vault__Crypto(), api=env.api).compact(b)             # ... and compacts

        x = Maintain__Raced(crypto=Vault__Crypto(), api=env.api)
        with pytest.raises(RuntimeError, match='moved while compacting'):
            x.compact(self.a)
        snaps = [Vault__Packs().parse_name(n.split('/')[-1]) for n in env.api.packs(self.vid, PACK_SNAPSHOTS)]
        newest_head = sync_b._init_components(b).ref_manager.read_ref(sync_b._init_components(b).ref_file_id, sync_b._init_components(b).read_key)
        assert any(s['commit_id'] == newest_head for s in snaps)             # Y's newer snapshot is still there
        sync_c, c = env.clone(self.key, 'c')                                  # and a fresh clone is complete
        assert env.tree(c) == env.tree(b)

    def test_a_newer_snapshot_is_never_superseded_by_an_older_head(self):
        packs = Vault__Packs(crypto=Vault__Crypto(), api=self.env.api)
        newer = packs.pack_name('obj-cas-imm-0000000000ee', 10, epoch_s=int(time.time()) + 100)
        self.env.api._store[f'{self.vid}/{PACK_SNAPSHOTS}{newer}'] = b'0' * 10   # a snapshot of a head this clone never saw
        plan = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api).compact(self.a, dry_run=True)['plan']
        assert newer not in [e['name'] for e in plan['superseded']]


class Test_Review_3_4__Members_Are_Stored_Objects_Only:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(2), vault_key=TEST_VAULT_KEY)
        self.vid  = _vid(self.sync, self.a)
        self.snap = self.env.api.packs(self.vid, PACK_SNAPSHOTS)[0]
        self.size = Vault__Packs().parse_name(self.snap)['size']

    def _serve(self, extra_members: list, compress=zipfile.ZIP_STORED):
        original = self.env.api.host_files(self.vid)[self.snap]
        buf = io.BytesIO(original)
        with zipfile.ZipFile(buf, 'a', compression=compress) as z:
            for name, body in extra_members:
                z.writestr(name, body, compress_type=compress)
        data = buf.getvalue()
        name = PACK_SNAPSHOTS + Vault__Packs().pack_name(Vault__Packs().parse_name(self.snap)['commit_id'], len(data), epoch_s=9999999999)
        self.env.api._store[f'{self.vid}/{name}'] = data
        return name

    def test_a_deflated_member_is_refused_without_being_inflated(self):
        bomb = b'\0' * (50 * 1024 * 1024)                                        # 50 MB of zeros: ~50 KB deflated
        oid  = Vault__Crypto().compute_object_id(bomb)                         # a correct id, so only the type check can refuse it
        self._serve([(f'bare/data/{oid}', bomb)], compress=zipfile.ZIP_DEFLATED)
        import tracemalloc
        tracemalloc.start()
        sync_b, b = self.env.clone(self.key, 'b')
        peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
        assert oid not in self.env.store_bytes(b)
        assert peak < 20 * 1024 * 1024, peak                                   # never inflated
        assert self.env.tree(b) == self.env.tree(self.a)

    def test_members_whose_names_are_not_content_addresses_are_refused(self):
        self._serve([('bare/data/not-an-id', b'x'), ('bare/data/.hidden', b'y'), ('bare/data/obj-cas-imm-zz', b'z')])
        sync_b, b = self.env.clone(self.key, 'b')
        data_dir = os.path.join(b, '.sg_vault', 'bare', 'data')
        assert not {'not-an-id', '.hidden', 'obj-cas-imm-zz'} & set(os.listdir(data_dir))

    def test_verify_reports_such_members_instead_of_raising(self):
        self._serve([('bare/data/not-an-id', b'x')])
        report = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api).verify(self.a)
        assert not report['ok'] and any('not a store object' in b['member'] for b in report['bad'])


class Test_Review_6__Tags_On_A_Pack_Vault:

    def test_tag_create_works_once_the_commit_is_pushed(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(2), vault_key=TEST_VAULT_KEY)
        tags = Vault__Sync__Tag(crypto=sync.crypto, api=env.api)
        tags.create(a, 'v1', message='first')
        assert any(t['name'] == 'v1' for t in tags.list_tags(a))
        env.write(a, {'later.md': b'later\n'}); later = sync.commit(a, message='later')['commit_id']
        with pytest.raises(Exception, match='not on the server yet'):
            tags.create(a, 'v2', commit_id=later)
        sync.push(a)
        tags.create(a, 'v2', commit_id=later)
        sync_b, b = env.clone(key, 'b')
        assert {t['name'] for t in Vault__Sync__Tag(crypto=sync_b.crypto, api=env.api).list_tags(b)} >= {'v1', 'v2'}


class Test_Review_7__Interrupted_First_Push:

    def test_a_first_push_that_fails_after_the_snapshot_is_still_a_first_push_when_retried(self):
        class Host__Refuses_Refs_Once(Host__Counting):
            allow = False                                                       # the first push's refs fail, batch and single
            def batch(self, vault_id, write_key, operations):
                if not self.allow and any(str(op.get('file_id', '')).startswith('bare/refs/') for op in operations):
                    raise RuntimeError('HTTP 503: try later')
                return super().batch(vault_id, write_key, operations)
            def write(self, vault_id, file_id, write_key, payload):
                if not self.allow and file_id.startswith('bare/refs/'):
                    raise RuntimeError('HTTP 503: try later')
                return super().write(vault_id, file_id, write_key, payload)

        env  = Pack__Env(Host__Refuses_Refs_Once().setup())
        sync = env.sync(); a = env.path()
        created = sync.init(a, vault_key=TEST_VAULT_KEY, packs=True)
        env.write(a, env.text_files(2)); sync.commit(a, message='first')
        with pytest.raises(Exception):
            sync.push(a)
        vid = _vid(sync, a)
        assert len(env.api.packs(vid, PACK_SNAPSHOTS)) == 1                     # the snapshot went up first ...
        assert not [f for f in env.api.host_files(vid) if f.startswith('bare/refs/')]   # ... the refs did not
        env.api.allow = True
        assert sync.push(a)['status'] == 'pushed'                               # the retry is a first push again
        assert len(env.api.packs(vid, PACK_SNAPSHOTS)) == 1                     # and reuses the snapshot
        sync_b, b = env.clone(created['vault_key'], 'b')
        assert env.tree(b) == env.tree(a)


class Test_Review__Clone_Family_And_Read_Only:

    def test_clone_branch_on_a_pack_vault_says_why_it_cannot(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(1), vault_key=TEST_VAULT_KEY)
        with pytest.raises(Exception, match='do not read packs yet'):
            env.sync().clone_branch(key, env.path('cb'))

    def test_compact_refuses_without_a_write_key(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(1), vault_key=TEST_VAULT_KEY)
        c    = sync._init_components(a)
        from sgit_ai.core.actions.clone.Vault__Sync__Clone import Vault__Sync__Clone
        read_only = env.path('ro')
        Vault__Sync__Clone(crypto=Vault__Crypto(), api=env.api).clone_read_only(c.vault_id, c.read_key.hex(), read_only)
        assert env.tree(read_only) == env.tree(a)                                 # a read-only clone takes the packs too
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=env.api)
        assert not maint._init_components(read_only).write_key
        with pytest.raises(RuntimeError, match='no write key'):
            maint.compact(read_only)
        sync_ro = env.sync()
        env.write(a, {'more.md': b'more\n'}); sync.commit(a, message='more'); sync.push(a)
        sync_ro.pull_read_only(read_only)                                       # and pulls commit packs
        assert env.tree(read_only) == env.tree(a)


class Test_Review_8__Ranged_Read_Lengths:

    def test_a_206_without_content_range_and_no_size_falls_back_to_one_stream(self, monkeypatch):
        import http.server, threading
        import sgit_ai.network.api.Vault__API as mod
        monkeypatch.setattr(mod, 'PRESIGNED_PART', 1000)
        body = bytes(range(256)) * 20

        class Handler(http.server.BaseHTTPRequestHandler):
            calls = []
            def log_message(self, *a): pass
            def do_GET(self):
                rng = self.headers.get('Range'); type(self).calls.append(rng)
                if rng:
                    start, end = [int(x) for x in rng.replace('bytes=', '').split('-')]
                    chunk = body[start:end + 1]; self.send_response(206)                  # no Content-Range
                else:
                    chunk = body; self.send_response(200)
                self.send_header('Content-Length', str(len(chunk))); self.end_headers(); self.wfile.write(chunk)

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            class API(Vault__API):
                def presigned_read_url(self, vault_id, file_id):
                    return {'url': f'http://127.0.0.1:{httpd.server_port}/x'}
            api = API(base_url='http://127.0.0.1:9'); api.setup()
            assert api.read_large('v', 'f') == body                               # whole file, not the first part
            assert Handler.calls == ['bytes=0-999', None]
        finally:
            httpd.shutdown()

    def test_a_short_range_is_an_error_not_a_truncated_file(self, monkeypatch):
        import http.server, threading
        import sgit_ai.network.api.Vault__API as mod
        monkeypatch.setattr(mod, 'PRESIGNED_PART', 1000)
        body = b'q' * 2500

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                rng = self.headers.get('Range')
                start, end = [int(x) for x in rng.replace('bytes=', '').split('-')]
                chunk = body[start:end + 1]
                if start == 1000:
                    chunk = chunk[:-1]                                          # one byte short, every time
                self.send_response(206); self.send_header('Content-Range', f'bytes {start}-{end}/{len(body)}')
                self.send_header('Content-Length', str(len(chunk))); self.end_headers(); self.wfile.write(chunk)

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            class API(Vault__API):
                def presigned_read_url(self, vault_id, file_id):
                    return {'url': f'http://127.0.0.1:{httpd.server_port}/x'}
            api = API(base_url='http://127.0.0.1:9'); api.setup()
            with pytest.raises(RuntimeError, match='expected 1000 bytes, got 999'):
                api.read_large('v', 'f', size=len(body))
        finally:
            httpd.shutdown()


class Test_Review_UX:

    def test_push_summary_counts_the_pack_members(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(1), vault_key=TEST_VAULT_KEY)
        sync_b, b = env.clone(key, 'b')
        env.write(b, {'one.md': b'one\n', 'two.md': b'two\n'}); sync_b.commit(b, message='two files')
        result = sync_b.push(b)
        assert result['objects_uploaded'] == 4 and result['commits_pushed'] == 1    # commit, root tree, two blobs


# ---------------------------------------------------------------------------
# Round 2 (same reviewer, on 801b890): N1 to N4 and the two UX items
# ---------------------------------------------------------------------------

class Test_Review_Round2__N1_Snapshot_Choice:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(2), vault_key=TEST_VAULT_KEY)
        self.vid = _vid(self.sync, self.a)
        self.sync_b, self.b = self.env.clone(self.key, 'b')
        self.env.write(self.b, {'b.md': b'b\n'}); self.sync_b.commit(self.b, message='b'); self.sync_b.push(self.b)
        self.sync.pull(self.a)

    def _snapshot_of(self, sync, d, epoch):
        """A snapshot pack for d's head, named with the given epoch, placed on the host."""
        packs = Vault__Packs(crypto=sync.crypto, api=self.env.api)
        c     = sync._init_components(d)
        head  = c.ref_manager.read_ref(c.ref_file_id, c.read_key)
        path, _ = packs.build_snapshot_pack(os.path.join(d, '.sg_vault'), head, c.read_key, os.path.join(self.env.root, 'w'))
        with open(path, 'rb') as f:
            data = f.read()
        name = packs.pack_name(head, len(data), epoch_s=epoch)
        self.env.api._store[f'{self.vid}/{PACK_SNAPSHOTS}{name}'] = data
        return name, head

    def test_a_stale_snapshot_with_the_newest_name_does_not_break_a_fresh_clone(self):
        # the host: S(c6) for the real head, S(c5) for an older head but with a LATER epoch (an aborted
        # compaction, or a skewed clock), and commits/ empty — N1's end state
        maint = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=self.env.api)
        maint.compact(self.b)                                                 # S(head) written, commit packs archived
        sync_old, old = self.env.clone(self.key, 'old')                       # a clone at the head ...
        self.env.write(self.b, {'c.md': b'c\n'}); self.sync_b.commit(self.b, message='c'); self.sync_b.push(self.b)
        maint.compact(self.b)                                                 # ... now one commit behind: S(c6) on the host
        stale, old_head = self._snapshot_of(sync_old, old, int(time.time()) + 1000)   # S(c5), newest by name
        self.env.api.reset_counts()
        sync_c, c = self.env.clone(self.key, 'c')
        assert self.env.tree(c) == self.env.tree(self.b)                      # complete: took the head's snapshot
        assert stale not in [f.split('/')[-1] for f in self.env.api.requested_ids]   # and never the stale one

    def test_an_aborted_compaction_takes_its_own_snapshot_back(self):
        env, sync_b, b = self.env, self.sync_b, self.b

        class Maintain__Raced(Vault__Pack_Maintain):
            def _moves_about_to_start(self, c):
                env.write(b, {'c.md': b'c\n'}); sync_b.commit(b, message='c'); sync_b.push(b)
                Vault__Pack_Maintain(crypto=Vault__Crypto(), api=env.api).compact(b)

        with pytest.raises(RuntimeError, match='snapshot just written was removed'):
            Maintain__Raced(crypto=Vault__Crypto(), api=env.api).compact(self.a)
        snaps = [Vault__Packs().parse_name(n.split('/')[-1])['commit_id'] for n in env.api.packs(self.vid, PACK_SNAPSHOTS)]
        head_b = sync_b._init_components(b).ref_manager.read_ref(sync_b._init_components(b).ref_file_id, sync_b._init_components(b).read_key)
        assert snaps == [head_b]                                              # only Y's snapshot remains
        sync_c, c = env.clone(self.key, 'c')
        assert env.tree(c) == env.tree(b)

    def test_a_clone_far_behind_walks_back_through_snapshots_until_the_head_is_complete(self):
        packs = Vault__Packs(crypto=Vault__Crypto(), api=self.env.api)
        # the head's own snapshot is absent; the newest snapshot is for an older head; commit packs carry the rest
        c_b  = self.sync_b._init_components(self.b)
        old_head = c_b.ref_manager.read_ref(c_b.ref_file_id, c_b.read_key)
        for n in self.env.api.packs(self.vid, PACK_SNAPSHOTS):                # drop the first-push snapshot
            del self.env.api._store[f'{self.vid}/{n}']
        self._snapshot_of(self.sync_b, self.b, int(time.time()))             # S(old head), the only snapshot
        self.env.write(self.b, {'d.md': b'd\n'}); self.sync_b.commit(self.b, message='d'); self.sync_b.push(self.b)   # a commit pack after it
        sync_c, c = self.env.clone(self.key, 'c')
        assert self.env.tree(c) == self.env.tree(self.b)
        assert packs.history_complete(os.path.join(c, '.sg_vault'), self.sync_b._init_components(self.b).ref_manager.read_ref(c_b.ref_file_id, c_b.read_key), c_b.read_key)


class Test_Review_Round2__N2_Duplicate_Members:

    def test_a_pack_with_a_name_twice_is_refused_whole_and_never_inflated(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(2), vault_key=TEST_VAULT_KEY)
        vid  = _vid(sync, a)
        snap = env.api.packs(vid, PACK_SNAPSHOTS)[0]
        original = env.api.host_files(vid)[snap]
        bomb = b'\0' * (50 * 1024 * 1024)
        oid  = Vault__Crypto().compute_object_id(bomb)
        buf  = io.BytesIO(original)
        with zipfile.ZipFile(buf, 'a') as z:
            z.writestr(f'bare/data/{oid}', b'decoy', compress_type=zipfile.ZIP_STORED)        # a stored decoy ...
            z.writestr(f'bare/data/{oid}', bomb, compress_type=zipfile.ZIP_DEFLATED)         # ... then the bomb, same name
        data = buf.getvalue()
        name = PACK_SNAPSHOTS + Vault__Packs().pack_name(Vault__Packs().parse_name(snap)['commit_id'], len(data), epoch_s=9999999999)
        env.api._store[f'{vid}/{name}'] = data
        packs = Vault__Packs(crypto=Vault__Crypto(), api=env.api)
        import tracemalloc
        tracemalloc.start()
        result = packs.extract_pack(data, os.path.join(env.path('x'), '.sg_vault'))
        peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
        assert result == dict(extracted=0, refused=['(duplicate member names)'])
        assert peak < 20 * 1024 * 1024
        report = Vault__Pack_Maintain(crypto=Vault__Crypto(), api=env.api).verify(a)
        assert not report['ok'] and any('duplicate' in b['member'] for b in report['bad'])


class Test_Review_Round2__N3_N4:

    def test_clone_range_on_a_pack_vault_says_why_it_cannot(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault(env.text_files(1), vault_key=TEST_VAULT_KEY)
        with pytest.raises(Exception, match='do not read packs yet'):
            env.sync().clone_range(key, env.path('cr'))

    def test_clone_headless_then_fetch_reads_a_pack_vault(self):
        env = Pack__Env()
        sync, a, key = env.pack_vault({'docs/f1.md': b'hello\n'}, vault_key=TEST_VAULT_KEY)
        h = env.path('headless')
        env.sync().clone_headless(key, h)
        assert not os.path.exists(os.path.join(h, 'docs', 'f1.md'))
        env.sync().sparse_fetch(h, path='docs/f1.md')                        # what `sgit fetch docs/f1.md` runs
        assert open(os.path.join(h, 'docs', 'f1.md'), 'rb').read() == b'hello\n'

    def test_the_gate_exemption_needs_every_feature_known(self):
        from sgit_ai.storage.Vault__Format import Vault__Format, Vault__Client_Too_Old_Error, FEATURE_PACKS
        from sgit_ai.schemas.Schema__Branch_Index import Schema__Branch_Index
        index = Schema__Branch_Index(schema='branch_index_v1', min_client='0.24.0', features=[FEATURE_PACKS])
        Vault__Format().check_client(index)                                   # this build carries 'packs'
        index.features = [FEATURE_PACKS, 'holograms']                         # and something it has never heard of
        fmt = Vault__Format()
        if fmt.parse_version(fmt.client_version()) and fmt.parse_version(fmt.client_version()) < (0, 24, 0):
            with pytest.raises(Vault__Client_Too_Old_Error):
                fmt.check_client(index)                                       # no exemption: refused by name
        assert fmt.gate_this_build_carries(index) == (0, 0, 0)


class Test_Review_Round2__UX:

    def test_status_after_import_says_never_pushed_and_counts_ahead(self):
        from sgit_ai.core.actions.pack.Vault__Pack_Convert import Vault__Pack_Convert
        env = Pack__Env()
        sync, normal, _ = env.normal_vault(env.text_files(2), vault_key=TEST_VAULT_KEYS[0])
        env.write(normal, {'two.md': b'two\n'}); sync.commit(normal, message='two'); sync.push(normal)
        packed = env.path('packed')
        Vault__Pack_Convert(crypto=Vault__Crypto(), api=env.api).convert(normal, packed, packs=True, vault_key=TEST_VAULT_KEYS[1])
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        CLI__Token_Store().save_base_url('http://127.0.0.1:9', packed)      # a configured remote, as the CLI records
        sync_p = env.sync()
        st = sync_p.status(packed)
        assert st['never_pushed'] is True and st['push_status'] == 'ahead' and st['ahead'] >= 3
        result = sync_p.push(packed)
        assert result['status'] == 'pushed' and result['commits_pushed'] >= 3 and result['objects_uploaded'] > 3
        st = sync_p.status(packed)
        assert st['never_pushed'] is False and st['push_status'] == 'up_to_date'

    def test_a_first_push_from_init_reports_its_commits_and_members(self):
        env = Pack__Env()
        sync = env.sync(); a = env.path()
        sync.init(a, vault_key=TEST_VAULT_KEY, packs=True)
        env.write(a, env.text_files(3)); sync.commit(a, message='first')
        result = sync.push(a)
        assert result['status'] == 'pushed' and result['commits_pushed'] == 2 and result['objects_uploaded'] >= 7
