"""A push of more than 100 commits uploads every one of them (cli.build BR-1, 0.26.6 review).

Before: push collected its commits with `Vault__Fetch.fetch_commit_chain(…, limit=100)`, so a push of 101 or more
new commits uploaded only the newest 100 with their trees and blobs, and moved the ref anyway. The older commits
lived only in the pushing clone; the next push stopped at the new remote head, so the gap never filled. A fresh
clone's fsck failed, `history log` stopped at the gap, and a merge whose base lay behind it had no base.

The scenario is cli.build's `push_gap.py`: one push of N commits, one more push, then a fresh clone walks the
whole history and runs fsck."""
import os
import shutil
import tempfile

import pytest

from sgit_ai.core.Vault__Sync                     import Vault__Sync
from sgit_ai.core.actions.fetch.Vault__Fetch      import Vault__Fetch
from sgit_ai.crypto.PKI__Crypto                   import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory    import Vault__API__In_Memory
from sgit_ai.storage.Vault__Commit                import Vault__Commit
from sgit_ai.storage.Vault__Object_Store          import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager           import Vault__Ref_Manager
from sgit_ai.storage.Vault__Sub_Tree              import Vault__Sub_Tree
from tests._helpers.vault_test_env                import TEST_VAULT_KEY


class Push__Gap_Scenario:

    def __init__(self, packs: bool = False):
        self.api  = Vault__API__In_Memory().setup()
        self.sync = Vault__Sync(crypto=Vault__Crypto(), api=self.api)
        self.root = tempfile.mkdtemp()
        self.a    = os.path.join(self.root, 'a')
        self.key  = self.sync.init(self.a, vault_key=TEST_VAULT_KEY, **(dict(packs=True) if packs else {}))['vault_key']

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, text: str, rel: str = 'x.txt'):
        with open(os.path.join(self.a, rel), 'w') as f:
            f.write(text)

    def commits(self, n: int, prefix: str = 'c'):
        for i in range(n):
            self.write(f'{prefix} {i}\n')
            self.sync.commit(self.a, message=f'{prefix}{i}')

    def fresh_clone(self, name: str = 'c') -> str:
        path = os.path.join(self.root, name)
        self.sync.clone(self.key, path)
        return path

    def walk(self, directory: str) -> tuple:
        """(commits walked along first parents from HEAD, the id the walk could not read or None)."""
        comp = self.sync._init_components(directory)
        vc   = Vault__Commit(crypto=self.sync.crypto, pki=PKI__Crypto(), object_store=comp.obj_store,
                             ref_manager=Vault__Ref_Manager())
        cid, walked = self.sync.resolve_revision(directory, 'HEAD'), 0
        while cid:
            try:
                commit = vc.load_commit(cid, comp.read_key)
            except Exception:
                return walked, cid
            walked += 1
            parents = [str(p) for p in (commit.parents or []) if str(p)]
            cid     = parents[0] if parents else None
        return walked, None


class Test_Push__Long_Chain:

    def setup_method(self):
        self.s = Push__Gap_Scenario()

    def teardown_method(self):
        self.s.cleanup()

    @pytest.mark.parametrize('n', [101, 150])
    def test_one_push_of_n_commits_reaches_the_host_whole(self, n):
        s = self.s
        s.write('0\n'); s.sync.commit(s.a, message='first'); s.sync.push(s.a)
        s.commits(n)
        s.sync.push(s.a)                                                # one push of n commits
        s.write('later\n'); s.sync.commit(s.a, message='later'); s.sync.push(s.a)
        clone          = s.fresh_clone()
        walked, broken = s.walk(clone)
        assert broken is None
        assert walked == n + 3                                          # init + first + n + later
        fsck = s.sync.fsck(clone)
        assert fsck['ok'] is True and not fsck.get('missing'), fsck

    def test_the_first_push_of_a_long_local_history(self):
        s = self.s
        s.commits(130)                                                  # never pushed: stop_at is the init commit
        s.sync.push(s.a)
        walked, broken = s.walk(s.fresh_clone())
        assert (walked, broken) == (131, None)

    def test_a_teammate_merges_across_a_long_push(self):
        s   = self.s
        s.write('base\n', 'shared.txt'); s.sync.commit(s.a, message='base'); s.sync.push(s.a)
        bob = s.fresh_clone('bob')
        s.commits(120)                                                  # alice: 120 commits to x.txt, one push
        s.sync.push(s.a)
        with open(os.path.join(bob, 'shared.txt'), 'w') as f:            # only a correct base makes this clean:
            f.write('bob\n')                                            # with none, shared.txt is an add/add conflict
        s.sync.commit(bob, message='bob')
        result = s.sync.pull(bob)                                       # the merge base lies below alice's 120
        assert result['status'] == 'merged', result
        with open(os.path.join(bob, 'x.txt')) as f:
            assert f.read() == 'c 119\n'
        with open(os.path.join(bob, 'shared.txt')) as f:
            assert f.read() == 'bob\n'


class Test_Push__Long_Chain__Pack_Vault:

    def test_one_push_of_150_commits(self):
        s = Push__Gap_Scenario(packs=True)
        try:
            s.write('0\n'); s.sync.commit(s.a, message='first'); s.sync.push(s.a)
            s.commits(150)
            s.sync.push(s.a)
            s.write('later\n'); s.sync.commit(s.a, message='later'); s.sync.push(s.a)
            clone = s.fresh_clone()
            assert s.walk(clone) == (153, None)
            assert s.sync.fsck(clone)['ok'] is True
        finally:
            s.cleanup()


class Test_Vault__Fetch__Chain_Has_No_Cap:
    """The chain push uploads: every commit reachable from the head and not from the stop commit."""

    def setup_method(self):
        self.crypto   = Vault__Crypto()
        self.dir      = tempfile.mkdtemp()
        self.store    = Vault__Object_Store(vault_path=self.dir, crypto=self.crypto)
        self.read_key = os.urandom(32)
        self.vc       = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=self.store,
                                      ref_manager=Vault__Ref_Manager())
        self.tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.store).build_from_flat({}, self.read_key)
        self.fetcher  = Vault__Fetch(crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def line(self, n: int, parent: str = None, start: int = 0) -> list:
        ids = []
        for i in range(n):
            parent = self.vc.create_commit(read_key=self.read_key, tree_id=self.tree, message=f'm{start + i}',
                                           parent_ids=[parent] if parent else [], timestamp_ms=1000 + start + i)
            ids.append(parent)
        return ids

    def test_more_than_100_new_commits(self):
        old   = self.line(5)
        new   = self.line(250, parent=old[-1], start=5)
        chain = self.fetcher.fetch_commit_chain(self.store, self.read_key, new[-1], stop_at=old[-1])
        assert chain == list(reversed(new)) + [old[-1]]                 # newest first, then the stop commit

    def test_more_than_100_commits_already_on_the_host(self):
        old   = self.line(300)                                           # the stop commit's history is long
        new   = self.line(3, parent=old[-1], start=300)
        chain = self.fetcher.fetch_commit_chain(self.store, self.read_key, new[-1], stop_at=old[-1])
        assert chain == list(reversed(new)) + [old[-1]]

    def test_a_merge_of_an_old_host_commit_uploads_only_what_is_new(self):
        old   = self.line(150)
        mine  = self.line(120, parent=old[-1], start=150)
        merge = self.vc.create_commit(read_key=self.read_key, tree_id=self.tree, message='merge',
                                      parent_ids=[mine[-1], old[10]], timestamp_ms=5000)
        chain = self.fetcher.fetch_commit_chain(self.store, self.read_key, merge, stop_at=old[-1])
        assert set(chain) == set(mine) | {merge, old[-1]}
        assert self.fetcher.missing_parents(chain, old[-1], self.store, self.read_key) == []

    def test_missing_parents_names_a_gap(self):
        old   = self.line(3)
        new   = self.line(4, parent=old[-1], start=3)
        assert self.fetcher.missing_parents(new[::-1][:2] + [old[-1]], old[-1], self.store, self.read_key) == [new[1]]


class Test_Check__Upload_History:
    """A gap an older build left on the host is filled from the clone that holds the commits."""

    def make_gap(self, s: Push__Gap_Scenario, packs: bool) -> list:
        """Push 30 commits, then remove 10 of the middle ones from the host as a build up to 0.26.8 would have
        left them: their commit objects and what they introduced (loose), or their commit packs (pack vault)."""
        s.write('0\n'); s.sync.commit(s.a, message='first'); s.sync.push(s.a)
        s.commits(30)
        s.sync.push(s.a)
        comp    = s.sync._init_components(s.a)
        chain   = Vault__Fetch(crypto=s.sync.crypto).fetch_commit_chain(comp.obj_store, comp.read_key,
                                                                         s.sync.resolve_revision(s.a, 'HEAD'))
        gap     = chain[10:20]
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        packer  = Vault__Packs(crypto=s.sync.crypto, api=s.api)
        for key in list(s.api._store):
            if packs:
                if '/bare/packs/' in key and any(cid in key for cid in gap):
                    del s.api._store[key]
            else:
                introduced = {o for cid in gap for o in packer.objects_introduced(comp.sg_dir, cid, comp.read_key)}
                if key.rsplit('/', 1)[-1] in introduced and '/bare/data/' in key:
                    del s.api._store[key]
        return gap

    @pytest.mark.parametrize('packs', [False, True])
    def test_upload_history_fills_the_gap(self, packs):
        s = Push__Gap_Scenario(packs=packs)
        try:
            gap = self.make_gap(s, packs)
            assert s.walk(s.fresh_clone('before'))[1] is not None               # the host's history is broken
            dry = s.sync.upload_history(s.a, dry_run=True)
            assert set(dry['missing_commits']) == set(gap) and dry['uploaded_objects'] == 0
            done = s.sync.upload_history(s.a)
            assert done['ok'] and done['uploaded_objects'] > 0
            clone = s.fresh_clone('after')
            assert s.walk(clone) == (32, None)                                   # init + first + 30: nothing lost
            assert s.sync.fsck(clone)['ok'] is True
            assert s.sync.upload_history(s.a)['missing_commits'] == []           # nothing left to do
        finally:
            s.cleanup()

    def test_the_cli(self, capsys):
        s = Push__Gap_Scenario()
        try:
            self.make_gap(s, packs=False)
            from sgit_ai.cli.CLI__Vault import CLI__Vault
            from types import SimpleNamespace
            vault = CLI__Vault()
            vault.create_sync = lambda base_url, token: s.sync
            vault.cmd_upload_history(SimpleNamespace(directory=s.a, dry_run=True))
            out = capsys.readouterr().out
            assert 'missing there.' in out and 'Dry run: nothing uploaded.' in out
            vault.cmd_upload_history(SimpleNamespace(directory=s.a, dry_run=False))
            assert 'Uploaded ' in capsys.readouterr().out
            vault.cmd_upload_history(SimpleNamespace(directory=s.a, dry_run=False))
            assert "The host holds this clone's whole history." in capsys.readouterr().out
        finally:
            s.cleanup()
