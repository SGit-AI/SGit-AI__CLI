"""Review of 00d6fc1, S5/S6: log filters walked the first-parent chain only (a commit
merged in from a second parent never matched) and were silently ignored with a
range, --files, --patch, --json or --file."""
import os
from types import SimpleNamespace

import pytest

from sgit_ai.cli.CLI__Vault                         import CLI__Vault
from sgit_ai.plugins.history.CLI__History           import CLI__History
from tests._helpers.vault_test_env                  import Vault__Test_Env


class Test_Review__Log_Filters:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()

    def teardown_method(self):
        self.s.cleanup()

    def _args(self, directory, **kw):
        base = dict(directory=directory, oneline=True, graph=False, limit=None, grep=None, since=None,
                    until=None, author=None, stat=False, vault_key=None, read_key=None)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_grep_finds_a_commit_merged_in_from_a_second_parent(self, capsys, monkeypatch):
        with open(os.path.join(self.s.bob_dir, 'b.md'), 'w') as f:
            f.write('bob')
        self.s.sync.commit(self.s.bob_dir, 'bobfix: the merged-in change')
        self.s.sync.push(self.s.bob_dir)
        with open(os.path.join(self.s.alice_dir, 'c.md'), 'w') as f:
            f.write('alice')
        self.s.sync.commit(self.s.alice_dir, 'alice work')
        self.s.sync.pull(self.s.alice_dir)                                   # three-way: bob's commit is parent 2
        monkeypatch.chdir(self.s.alice_dir)
        CLI__Vault().cmd_inspect_log(self._args(self.s.alice_dir, grep='bobfix'))
        assert 'bobfix: the merged-in change' in capsys.readouterr().out

    @pytest.mark.parametrize('extra', [dict(range_spec='HEAD~1..HEAD'), dict(json_out=True), dict(files=True)])
    def test_a_filter_is_never_silently_ignored(self, extra, capsys):
        args = SimpleNamespace(directory=self.s.alice_dir, range_spec='', graph=False, files=False, patch=False,
                               json_out=False, file_path=None, grep='x', since=None, until=None, author=None)
        for k, v in extra.items():
            setattr(args, k, v)
        with pytest.raises(SystemExit):
            CLI__History()._dispatch_log(args)
        assert 'work with the plain log only' in capsys.readouterr().err
