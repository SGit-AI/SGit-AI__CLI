"""Push must upload the blobs of every commit it pushes, not only HEAD's.

Before: a file created in commit 1 and changed in commit 2, pushed together,
left commit 1's blob referenced by an uploaded tree but never uploaded —
41 such objects on the DC vault after four days of agent runs."""
import os
from tests._helpers.vault_test_env       import Vault__Test_Env
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
from sgit_ai.storage.Vault__Commit       import Vault__Commit
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree     import Vault__Sub_Tree


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class _TwoClones:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.txt': 'a v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        self.vault_id = keys['vault_id']; self.rk = keys['read_key_bytes']

    def teardown_method(self):
        self.env.cleanup()

    def _reachable_blobs(self, directory):
        """Every blob id referenced by any commit reachable from the clone HEAD."""
        crypto = Vault__Crypto()
        store  = Vault__Object_Store(vault_path=os.path.join(directory, '.sg_vault'), crypto=crypto)
        vc     = Vault__Commit(crypto=crypto, pki=PKI__Crypto(), object_store=store, ref_manager=None)
        st     = Vault__Sub_Tree(crypto=crypto, obj_store=store)
        head   = self.sync.status(directory)['clone_head'] if 'clone_head' in self.sync.status(directory) else None
        if head is None:
            import json
            cfg  = json.load(open(os.path.join(directory, '.sg_vault', 'local', 'config.json')))
            head = None
        # walk from every ref in the local store instead — robust to field names
        refs_dir = os.path.join(directory, '.sg_vault', 'bare', 'refs')
        from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
        rm = Vault__Ref_Manager(vault_path=os.path.join(directory, '.sg_vault'), crypto=crypto)
        blobs, seen = set(), set()
        queue = [rm.read_ref(r, self.rk) for r in os.listdir(refs_dir)]
        while queue:
            cid = queue.pop()
            if not cid or cid in seen: continue
            seen.add(cid)
            c = vc.load_commit(cid, self.rk)
            for e in st.flatten(str(c.tree_id), self.rk).values():
                if e.get('blob_id'): blobs.add(e['blob_id'])
            queue.extend(str(p) for p in (c.parents or []))
        return blobs

    def _on_server(self, blob_id):
        return f'{self.vault_id}/bare/data/{blob_id}' in self.env.api._store


class Test_Push__Uploads_Blobs_Of_Every_Pushed_Commit(_TwoClones):

    def test_intermediate_version_is_uploaded(self):
        _write(self.alice, 'f.txt', 'f v1'); self.sync.commit(self.alice, message='f v1')
        _write(self.alice, 'f.txt', 'f v2'); self.sync.commit(self.alice, message='f v2')
        self.sync.push(self.alice)
        blobs = self._reachable_blobs(self.alice)
        missing = sorted(b for b in blobs if not self._on_server(b))
        assert missing == []                                   # before the fix: f v1's blob

    def test_file_added_then_deleted_before_push_is_still_uploaded(self):
        _write(self.alice, 'tmp.txt', 'short-lived'); self.sync.commit(self.alice, message='add tmp')
        os.remove(os.path.join(self.alice, 'tmp.txt'));  self.sync.commit(self.alice, message='rm tmp')
        self.sync.push(self.alice)
        assert all(self._on_server(b) for b in self._reachable_blobs(self.alice))

    def test_bob_clone_after_multi_commit_push_has_complete_history(self):
        for i in range(4):
            _write(self.alice, 'doc.md', f'doc v{i}'); self.sync.commit(self.alice, message=f'doc v{i}')
        self.sync.push(self.alice)
        self.sync.pull(self.bob)
        fsck = self.sync.fsck(self.bob) if hasattr(self.sync, 'fsck') else None
        if fsck is not None:
            assert not fsck.get('missing'), fsck
        assert all(self._on_server(b) for b in self._reachable_blobs(self.bob))

    def test_blob_already_on_remote_head_is_not_reuploaded(self):
        # the dedupe against the remote HEAD tree still applies
        _write(self.alice, 'b.txt', 'b v1'); self.sync.commit(self.alice, message='b v1'); self.sync.push(self.alice)
        before = len(self.env.api._store)
        _write(self.alice, 'c.txt', 'c v1'); self.sync.commit(self.alice, message='c v1'); self.sync.push(self.alice)
        added = len(self.env.api._store) - before
        assert added <= 4                                      # c blob + root tree + commit (+ pushed ref/meta), not a.txt/b.txt again
