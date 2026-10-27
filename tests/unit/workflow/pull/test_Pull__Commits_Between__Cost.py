"""QA round 2, note 1: the pull's commit list must not walk the base's whole history.
The two-sided walk expands the base side only within the clock-skew window below the
oldest new commit, so the cost follows the new commits; and it stays exact for a clock
up to that far behind (round 1, finding 3)."""
from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull, COMMIT_CLOCK_SKEW_MS
from sgit_ai.storage.Vault__Commit                 import Vault__Commit
from tests._helpers.pack_env                       import Pack__Env
from tests._helpers.vault_test_env                 import TEST_VAULT_KEY

HOUR = 3600 * 1000


class Commit__Counting(Vault__Commit):
    loads : int = 0
    def load_commit(self, commit_id, read_key):
        self.loads += 1
        return super().load_commit(commit_id, read_key)


class Test_Commits_Between__Cost:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.d, _ = self.env.normal_vault({'f.txt': b'f\n'}, vault_key=TEST_VAULT_KEY)
        self.c    = self.sync._init_components(self.d)
        self.vc   = Commit__Counting(crypto=self.sync.crypto, pki=self.c.pki, object_store=self.c.obj_store, ref_manager=self.c.ref_manager)
        head0     = self.c.ref_manager.read_ref(self.c.ref_file_id, self.c.read_key)
        self.tree = str(self.vc.load_commit(head0, self.c.read_key).tree_id)
        self.pull = Vault__Sync__Pull(crypto=self.sync.crypto, api=self.env.api)
        self.chain = [head0]                                       # 300 commits, one an hour: 12.5 days of history
        for i in range(300):
            self.chain.append(self._commit([self.chain[-1]], (i + 1) * HOUR, f'c{i}'))

    def _commit(self, parents, ts, msg):
        return self.vc.create_commit(self.c.read_key, self.tree, parent_ids=parents, message=msg, timestamp_ms=ts)

    def _between(self, head, base):
        self.vc.loads = 0
        return [s for s, _, _ in self.pull._commits_between(self.vc, self.c.read_key, head, base, self.c.obj_store)]

    def test_one_new_commit_loads_a_days_worth_of_base_not_the_history(self):
        assert self._between(self.chain[-1], self.chain[-2]) == [self.chain[-1][12:]]
        assert self.vc.loads <= COMMIT_CLOCK_SKEW_MS // HOUR + 3                 # ~25, not 300

    def test_three_new_commits(self):
        assert self._between(self.chain[-1], self.chain[-4]) == [c[12:] for c in self.chain[-1:-4:-1]]
        assert self.vc.loads <= COMMIT_CLOCK_SKEW_MS // HOUR + 6

    def test_nothing_new_loads_almost_nothing(self):
        assert self._between(self.chain[-1], self.chain[-1]) == []
        assert self.vc.loads <= 2

    def test_exact_for_a_clock_up_to_the_window_behind(self):
        """Base B dated 23 h before its own parent A: still exact. The head is a merge."""
        A = self._commit([self.chain[-1]], 400 * HOUR, 'A')
        B = self._commit([A], 400 * HOUR - 23 * HOUR, 'B')
        X = self._commit([A], 401 * HOUR, 'X')
        H = self._commit([X, B], 402 * HOUR, 'H')
        assert self._between(H, B) == [H[12:], X[12:]]
        assert self.vc.loads < 60
