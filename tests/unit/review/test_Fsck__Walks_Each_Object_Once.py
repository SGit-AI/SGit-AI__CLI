"""fsck verified every tree once per commit that reached it (282,202 checks for 8,589 trees,
270 s on the DC vault). A tree is the same object whichever commit reaches it: once is enough."""
import os
from tests._helpers.vault_test_env import Vault__Test_Env


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_Fsck__Walks_Each_Object_Once:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_single_vault(files={'a.txt': 'a', 'docs/b.md': 'b', 'docs/sub/c.md': 'c'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env = self._env.restore(); self.sync = self.env.sync; self.d = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_tree_count_is_unique_trees_not_trees_times_commits(self):
        for i in range(4):                                   # 4 more commits, docs/sub/ never changes
            _write(self.d, 'a.txt', f'a{i}'); self.sync.commit(self.d, message=f'c{i}')
        steps = []
        result = self.sync.fsck(self.d, on_progress=lambda ev, msg, *a: steps.append(msg))
        assert result['ok'] is True and result['missing'] == [] and result['corrupt'] == []
        checked = next(m for m in steps if m.startswith('Checked '))
        n_commits, n_trees = (int(w) for w in checked.replace(',', '').split() if w.isdigit())
        assert n_commits == 6                                # init's empty commit + initial + 4
        # unique trees: the empty tree, 5 root trees, up to 5 docs/ trees, 1 docs/sub/ tree — never 6× that
        assert n_trees <= 12, checked
        assert n_trees < n_commits * 3, checked
