"""Tests for `sgit resolve --show` 3-way verdict view (A4) — CLI print path."""
import os
import shutil
import tempfile
import types

import pytest

from sgit_ai.cli.CLI__Merge                            import CLI__Merge
from sgit_ai.core.Vault__Sync                          import Vault__Sync
from sgit_ai.core.actions.merge.Vault__Merge__State    import Vault__Merge__State
from sgit_ai.crypto.Vault__Crypto                      import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory         import Vault__API__In_Memory


class Test_CLI__Merge__Resolve_Show:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        cls.api    = Vault__API__In_Memory(); cls.api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=cls.api)
        cls.tmp    = tempfile.mkdtemp(prefix='resolve_show_')
        cls.vault  = os.path.join(cls.tmp, 'vault')
        cls.sync.init(cls.vault)

        def write(rel, content):
            with open(os.path.join(cls.vault, rel), 'w') as f:
                f.write(content)

        write('hot.txt', 'base line\n'); write('side.txt', 's0')
        cls.base   = cls.sync.commit(cls.vault, message='base')['commit_id']
        write('side.txt', 's1')                       # hot.txt left untouched vs base
        cls.ours2  = cls.sync.commit(cls.vault, message='ours side-only')['commit_id']
        write('hot.txt', 'theirs line\n')
        cls.theirs = cls.sync.commit(cls.vault, message='theirs')['commit_id']
        write('hot.txt', 'ours line\n')
        cls.ours   = cls.sync.commit(cls.vault, message='ours')['commit_id']

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _stage_merge(self, ours, theirs, lca, conflicts):
        mgr = Vault__Merge__State()
        mgr.write(self.vault, mgr.new_state(ours, theirs, lca, conflicts))

    def teardown_method(self):
        Vault__Merge__State().delete(self.vault)

    def _cli(self):
        return CLI__Merge(crypto=self.crypto, api=self.api)

    def _run_show(self, capsys):
        args = types.SimpleNamespace(show=True, all=False, ours=False, theirs=False,
                                     file=None, directory=self.vault)
        self._cli().cmd_resolve(args)
        return capsys.readouterr().out

    def test_genuine_conflict_shows_verdict_and_diff(self, capsys):
        self._stage_merge(self.ours, self.theirs, self.base, ['hot.txt'])
        out = self._run_show(capsys)
        assert 'hot.txt'   in out
        assert 'GENUINE'   in out
        assert 'ours line'   in out          # unified diff body
        assert 'theirs line' in out
        assert 'Verdict: 1 genuine' in out

    def test_one_sided_conflict_flagged_suspect(self, capsys):
        # ours2 left hot.txt unchanged vs base; only theirs changed it
        self._stage_merge(self.ours2, self.theirs, self.base, ['hot.txt'])
        out = self._run_show(capsys)
        assert 'ONE-SIDED' in out
        assert 'SUSPECT'   in out
        assert 'stale merge base' in out

    def test_no_merge_in_progress_raises(self):
        args = types.SimpleNamespace(show=True, all=False, ours=False, theirs=False,
                                     file=None, directory=self.vault)
        with pytest.raises(RuntimeError, match='No merge in progress'):
            self._cli().cmd_resolve(args)
