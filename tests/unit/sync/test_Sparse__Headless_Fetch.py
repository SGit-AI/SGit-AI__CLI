"""`sgit clone-headless` then `fetch` / `ls` / `cat` (issue 3, 14 Oct report): a headless
clone holds keys and config only, so the sparse commands used to fail on the missing
branch index. They now bring the tracked head down first (index, ref, commits, trees —
never blobs), the way `clone --sparse` does, then fetch what was asked."""
import os

import pytest

from sgit_ai.core.Vault__Sync          import Vault__Sync
from tests._helpers.vault_test_env     import Vault__Test_Env


class Test_Sparse__Headless_Fetch:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'hello', 'docs/guide.md': 'guide', 'docs/notes.md': 'notes'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s    = self._env.restore()
        self.sync = Vault__Sync(crypto=self.s.crypto, api=self.s.api)
        self.dir  = os.path.join(self.s.tmp_dir, 'headless')
        self.sync.clone_headless(self.s.vault_key, self.dir)

    def teardown_method(self):
        self.s.cleanup()

    def _objects(self):
        data = os.path.join(self.dir, '.sg_vault', 'bare', 'data')
        return set(os.listdir(data)) if os.path.isdir(data) else set()

    def test_a_headless_clone_starts_with_nothing(self):
        assert not os.path.isdir(os.path.join(self.dir, '.sg_vault', 'bare'))
        assert not os.path.exists(os.path.join(self.dir, 'readme.md'))

    def test_fetch_one_file_downloads_that_file(self):
        result = self.sync.sparse_fetch(self.dir, path='docs/guide.md')
        assert result['written'] == ['docs/guide.md']
        assert open(os.path.join(self.dir, 'docs', 'guide.md')).read() == 'guide'
        assert not os.path.exists(os.path.join(self.dir, 'readme.md'))             # only what was asked
        blobs_local = [o for o in self._objects() if self.s.sync._init_components(self.dir).obj_store.exists(o)]
        assert len(blobs_local) >= 1

    def test_ls_and_cat_work_and_a_second_call_makes_no_structural_request(self, monkeypatch):
        entries = self.sync.sparse_ls(self.dir)
        assert {str(e['path']) if isinstance(e, dict) else str(e.path) for e in entries} >= {'readme.md', 'docs/guide.md', 'docs/notes.md'}
        assert self.sync.sparse_cat(self.dir, 'readme.md') == b'hello'
        api   = self.s.api
        calls = []
        real  = api.batch_read
        monkeypatch.setattr(api, 'batch_read', lambda v, ids, failures=None: (calls.append(list(ids)), real(v, ids, failures=failures))[1])
        self.sync.sparse_ls(self.dir)                                                # everything structural is local now
        assert all(not fid.startswith(('bare/indexes/', 'bare/refs/')) for ids in calls for fid in ids)

    def test_fetch_all_then_everything_is_there(self):
        self.sync.sparse_fetch(self.dir)
        for rel, content in (('readme.md', 'hello'), ('docs/guide.md', 'guide'), ('docs/notes.md', 'notes')):
            assert open(os.path.join(self.dir, rel)).read() == content
