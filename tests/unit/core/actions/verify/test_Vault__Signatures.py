"""Tests for Vault__Signatures — where a commit's public key comes from and the status each
case gets (verified / bad / unsigned / no-key / missing), on a real vault with real
ECDSA signatures; key_fetch is None, so only local keys count."""
import json
import os
import shutil

from tests._helpers.vault_test_env                        import Vault__Test_Env
from sgit_ai.core.actions.verify.Vault__Signatures        import (Vault__Signatures, VERIFIED, BAD,
                                                                  UNSIGNED, NO_KEY, MISSING)
from sgit_ai.storage.Vault__Commit                        import Vault__Commit


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_Vault__Signatures:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_single_vault(files={'a.txt': 'a'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env  = self._env.restore(); self.sync = self.env.sync; self.d = self.env.vault_dir
        self.c    = self.sync._init_components(self.d)
        self.sigs = Vault__Signatures(crypto=self.env.crypto)
        self.vc   = Vault__Commit(crypto=self.env.crypto, pki=self.c.pki, object_store=self.c.obj_store,
                                  ref_manager=self.c.ref_manager)
        self.head = self.env.commit_id

    def teardown_method(self):
        self.env.cleanup()

    def _commit_json(self, cid: str) -> dict:
        return json.loads(self.env.crypto.decrypt(self.c.read_key, self.c.obj_store.load(cid)))

    def _store_commit(self, data: dict) -> str:
        return self.c.obj_store.store(self.env.crypto.encrypt(self.c.read_key, json.dumps(data).encode()))

    # ── status_of ───────────────────────────────────────────────────────
    def test_the_head_of_a_fresh_vault_is_verified_from_its_own_author_key(self):
        commit = self.vc.load_commit(self.head, self.c.read_key)
        assert commit.author_key_id and self.c.key_manager.key_exists(str(commit.author_key_id))
        assert self.sigs.status_of(self.c, self.c.read_key, self.head) == VERIFIED

    def test_a_commit_this_clone_does_not_hold_is_missing(self):
        assert self.sigs.status_of(self.c, self.c.read_key, 'obj-cas-imm-000000000000') == MISSING

    def test_a_commit_without_a_signature_is_unsigned(self):
        cid = self.vc.create_commit(read_key=self.c.read_key, tree_id=str(self.vc.load_commit(self.head, self.c.read_key).tree_id),
                                    parent_ids=[self.head], message='unsigned')
        assert self.sigs.status_of(self.c, self.c.read_key, cid) == UNSIGNED

    def test_author_key_the_vault_does_not_hold_is_no_key_without_a_fetcher(self):
        commit = self.vc.load_commit(self.head, self.c.read_key)
        os.remove(self.c.key_manager._key_path(str(commit.author_key_id)))
        assert self.sigs.status_of(self.c, self.c.read_key, self.head) == NO_KEY

    def test_a_key_file_that_does_not_decrypt_is_no_key(self):
        """A key file the host replaced with bytes the read key cannot open counts as no key."""
        commit = self.vc.load_commit(self.head, self.c.read_key)
        with open(self.c.key_manager._key_path(str(commit.author_key_id)), 'wb') as f:
            f.write(b'not a key file')
        assert self.sigs.status_of(self.c, self.c.read_key, self.head) == NO_KEY

    def test_a_tampered_signed_commit_is_bad(self):
        data = self._commit_json(self.head); data['message_enc'] = None; data['message'] = 'rewritten'
        cid  = self._store_commit(data)
        assert self.sigs.status_of(self.c, self.c.read_key, cid) == BAD

    def test_without_author_key_id_the_key_comes_from_the_branch_index(self):
        """An older commit carries no author_key_id: its branch's public_key_id (from the
        index) is used. The signature was made over a form that included the key id, so
        it no longer verifies: bad, not no-key."""
        data  = self._commit_json(self.head); data.pop('author_key_id', None)
        cid   = self._store_commit(data)
        index = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
        assert self.sigs.status_of(self.c, self.c.read_key, cid, index=index) == BAD
        assert self.sigs.status_of(self.c, self.c.read_key, cid, index=None) == NO_KEY   # no index: no key at all

    def test_without_author_key_id_and_without_branch_id_there_is_no_key(self):
        data = self._commit_json(self.head); data.pop('author_key_id', None); data['branch_id'] = None
        cid  = self._store_commit(data)
        index = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
        assert self.sigs.status_of(self.c, self.c.read_key, cid, index=index) == NO_KEY

    # ── verify_chain ────────────────────────────────────────────────────
    def test_verify_chain_walks_every_parent_and_loads_the_index_itself(self):
        for i in range(2):
            _write(self.d, 'a.txt', f'a{i}'); self.sync.commit(self.d, message=f'c{i}')
        head   = self.c.ref_manager.read_ref(str(self.c.branch_manager.get_branch_by_id(
            self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key),
            str(self.sync._read_local_config(self.d, self.c.storage).my_branch_id)).head_ref_id), self.c.read_key)
        report = self.sigs.verify_chain(self.c, self.c.read_key, head)
        assert report['total'] == 4                                   # init's empty commit + initial + 2
        assert report['counts'] == {VERIFIED: 4, BAD: 0, UNSIGNED: 0, NO_KEY: 0, MISSING: 0}
        assert report['first_failure'] is None and report['by_status'][VERIFIED][0] == head

    def test_verify_chain_tolerates_an_unreadable_index(self):
        """With the index gone, index=None: commits with their own author_key_id still verify."""
        shutil.rmtree(os.path.join(self.c.sg_dir, 'bare', 'indexes'))
        report = self.sigs.verify_chain(self.c, self.c.read_key, self.head)
        assert report['counts'][VERIFIED] == report['total'] == 2

    def test_verify_chain_reports_the_first_failure_and_stops_at_a_missing_parent(self):
        data = self._commit_json(self.head); data['parents'] = ['obj-cas-imm-000000000000']; data['message'] = 'x'
        cid  = self._store_commit(data)
        report = self.sigs.verify_chain(self.c, self.c.read_key, cid)
        assert report['first_failure'] == (cid, BAD)
        assert report['counts'][MISSING] == 1 and report['total'] == 2

    def test_verify_chain_stop_at_and_boundaries_and_an_empty_head(self):
        report = self.sigs.verify_chain(self.c, self.c.read_key, self.head, boundaries={self.head})
        assert report['total'] == 1                                   # classified, not expanded
        report = self.sigs.verify_chain(self.c, self.c.read_key, self.head, stop_at={self.head})
        assert report['total'] == 0                                   # neither classified nor expanded
        assert self.sigs.verify_chain(self.c, self.c.read_key, '')['total'] == 0

    def test_verify_chain_limit_counts_one_more_than_it_classifies(self):
        """Pins what the code does today: `limit` adds the commit that trips it to `seen`
        before breaking, so total is limit + 1 while the counts sum to limit."""
        for i in range(2):
            _write(self.d, 'a.txt', f'a{i}'); self.sync.commit(self.d, message=f'c{i}')
        head   = self.sync.history_log(self.d)[0]['commit_id'] if hasattr(self.sync, 'history_log') else None
        if head is None:
            index = self.c.branch_manager.load_branch_index(self.d, self.c.branch_index_file_id, self.c.read_key)
            meta  = self.c.branch_manager.get_branch_by_id(index, str(self.sync._read_local_config(self.d, self.c.storage).my_branch_id))
            head  = self.c.ref_manager.read_ref(str(meta.head_ref_id), self.c.read_key)
        report = self.sigs.verify_chain(self.c, self.c.read_key, head, limit=2)
        assert sum(report['counts'].values()) == 2
        assert report['total'] == 3
