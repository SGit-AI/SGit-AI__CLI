"""Tests for Vault__Diff.ensure_commit_local (A3 — read-only on-demand fetch).

Inspecting a commit whose objects were never cloned should fetch them read-only
(no merge, no `sgit pull`). Reproduced by pushing to an in-memory server, deleting
a local object, and confirming the on-demand fetch restores it.
"""
import os
import shutil
import tempfile
import types

import pytest

from sgit_ai.cli.CLI__Diff                          import CLI__Diff
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.diff.Vault__Diff          import Vault__Diff
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory


class Test_Vault__Diff__On_Demand_Fetch:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        cls.api    = Vault__API__In_Memory(); cls.api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=cls.api)
        cls.tmp    = tempfile.mkdtemp(prefix='on_demand_')
        cls.vault  = os.path.join(cls.tmp, 'vault')
        cls.sync.init(cls.vault)

        with open(os.path.join(cls.vault, 'a.txt'), 'w') as f:
            f.write('alpha\n')
        cls.commit_a = cls.sync.commit(cls.vault, message='A')['commit_id']
        with open(os.path.join(cls.vault, 'b.txt'), 'w') as f:
            f.write('beta\n')
        cls.commit_b = cls.sync.commit(cls.vault, message='B')['commit_id']
        cls.sync.push(cls.vault)                       # all objects now on the server

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _obj_path(self, oid):
        return os.path.join(self.vault, '.sg_vault', 'bare', 'data', oid)

    def test_no_api_cannot_fetch_and_show_fails(self):
        target = self._obj_path(self.commit_b)
        assert os.path.isfile(target)
        os.remove(target)                              # simulate "never cloned this object"
        try:
            diff = Vault__Diff(crypto=self.crypto)     # no api wired
            assert diff.ensure_commit_local(self.vault, self.commit_b) is False
            with pytest.raises(FileNotFoundError):
                diff.show_commit(self.vault, self.commit_b)
        finally:
            # restore for independence (re-fetch via api)
            Vault__Diff(crypto=self.crypto, api=self.api).ensure_commit_local(
                self.vault, self.commit_b)

    def test_on_demand_fetch_restores_object_and_show_works(self):
        target = self._obj_path(self.commit_b)
        os.remove(target)
        assert not os.path.isfile(target)

        diff = Vault__Diff(crypto=self.crypto, api=self.api)
        assert diff.ensure_commit_local(self.vault, self.commit_b) is True
        assert os.path.isfile(target)                  # re-downloaded read-only

        commit_info, result = diff.show_commit(self.vault, self.commit_b)
        assert self.commit_b in str(commit_info['commit_id'])

    def test_cli_try_fetch_returns_false_when_unwired(self):
        # CLI__Diff with no vault_ref/token_store cannot build an api → no fetch
        cli  = CLI__Diff()
        diff = Vault__Diff(crypto=self.crypto)
        args = types.SimpleNamespace(directory=self.vault)
        assert cli._try_fetch_commits(diff, self.vault, [self.commit_b], args) is False
