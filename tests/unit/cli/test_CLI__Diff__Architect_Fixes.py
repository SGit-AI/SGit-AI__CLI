"""Tests for the architect's F1 / F3 / F5 fixes on top of A3 + A4.

F1 — Vault__Diff._init_components must work on a READ_ONLY clone (no vault_key).
F3 — _on_demand_api must NOT fire when no real remote is configured.
F5 — wired on-demand retry through cmd_diff/cmd_show, plus A4 missing-base fallback.
"""
import os
import shutil
import sys
import tempfile
import types

import pytest

from sgit_ai.cli.CLI__Diff                             import CLI__Diff
from sgit_ai.cli.CLI__Merge                            import CLI__Merge
from sgit_ai.cli.CLI__Token_Store                      import CLI__Token_Store
from sgit_ai.cli.CLI__Vault                            import CLI__Vault
from sgit_ai.core.Vault__Sync                          import Vault__Sync
from sgit_ai.core.actions.diff.Vault__Diff             import Vault__Diff
from sgit_ai.core.actions.merge.Vault__Merge__State    import Vault__Merge__State
from sgit_ai.crypto.Vault__Crypto                      import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory         import Vault__API__In_Memory


# ---------------------------------------------------------------------------
# F1 — read-only clone: Vault__Diff must derive keys from clone_mode.json
# ---------------------------------------------------------------------------

class Test_Vault__Diff__ReadOnly_Clone:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        cls.api    = Vault__API__In_Memory(); cls.api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=cls.api)
        cls.tmp    = tempfile.mkdtemp(prefix='ro_diff_')

        # Producer vault: commit + push so a published named branch exists.
        producer = os.path.join(cls.tmp, 'producer')
        cls.sync.init(producer)
        with open(os.path.join(producer, 'hello.txt'), 'w') as f:
            f.write('hi\n')
        cls.commit_id = cls.sync.commit(producer, message='hello')['commit_id']
        cls.sync.push(producer)
        # Read the vault_key the producer derived (to compute read_key for the RO clone).
        with open(os.path.join(producer, '.sg_vault', 'local', 'vault_key')) as f:
            vk = f.read().strip()
        keys = cls.crypto.derive_keys_from_vault_key(vk)
        cls.vault_id      = keys['vault_id']
        cls.read_key_hex  = keys['read_key']

        # Read-only clone target.
        cls.ro_dir = os.path.join(cls.tmp, 'ro_clone')
        cls.sync.clone_read_only(cls.vault_id, cls.read_key_hex, cls.ro_dir)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_no_vault_key_on_disk(self):
        # 06/04 read-only-clone contract: RO clones do NOT have local/vault_key.
        assert not os.path.isfile(
            os.path.join(self.ro_dir, '.sg_vault', 'local', 'vault_key'))

    def test_diff_init_components_works_on_ro_clone(self):
        # Before F1 this raised FileNotFoundError on local/vault_key.
        c = Vault__Diff(crypto=self.crypto)._init_components(self.ro_dir)
        assert c.vault_id      == self.vault_id
        assert c.read_key      is not None

    def test_ensure_commit_local_no_longer_swallows_on_ro_clone(self):
        # The whole A3 promise: a RO clone can inspect a commit on demand.
        diff = Vault__Diff(crypto=self.crypto, api=self.api)
        assert diff.ensure_commit_local(self.ro_dir, self.commit_id) is True


# ---------------------------------------------------------------------------
# F3 — no-remote vaults must NOT contact the default API host
# ---------------------------------------------------------------------------

class Test_CLI__Diff__On_Demand_Gating:

    def _wired_cli(self):
        """Build a CLI__Diff wired like CLI__Main.build_parser does."""
        api = Vault__API__In_Memory(); api.setup()
        cli = CLI__Diff()
        cli.vault_ref   = CLI__Vault(api=api, token_store=CLI__Token_Store())
        cli.token_store = cli.vault_ref.token_store
        return cli

    def test_no_remote_configured_returns_none(self, tmp_path):
        # A purely-local vault dir with no remote config → no api built.
        cli  = self._wired_cli()
        args = types.SimpleNamespace(directory=str(tmp_path),
                                     remote=None, base_url=None, verify_tls=None)
        assert cli._on_demand_api(str(tmp_path), args) is None

    def test_explicit_base_url_override_does_build_api(self, tmp_path):
        cli  = self._wired_cli()
        args = types.SimpleNamespace(directory=str(tmp_path),
                                     remote=None,
                                     base_url='http://example.invalid',   # forces name='--base-url'
                                     verify_tls=None, token=None)
        api  = cli._on_demand_api(str(tmp_path), args)
        # Build succeeds even though host is invalid — the network call is lazy.
        assert api is not None


# ---------------------------------------------------------------------------
# F5 — wired retry through cmd_show / cmd_diff (the real user path)
# ---------------------------------------------------------------------------

class Test_CLI__Diff__Wired_Retry:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        cls.api    = Vault__API__In_Memory(); cls.api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=cls.api)
        cls.tmp    = tempfile.mkdtemp(prefix='wired_retry_')
        cls.vault  = os.path.join(cls.tmp, 'v')
        cls.sync.init(cls.vault)
        with open(os.path.join(cls.vault, 'a.txt'), 'w') as f:
            f.write('alpha\n')
        cls.commit_a = cls.sync.commit(cls.vault, message='A')['commit_id']
        with open(os.path.join(cls.vault, 'b.txt'), 'w') as f:
            f.write('beta\n')
        cls.commit_b = cls.sync.commit(cls.vault, message='B')['commit_id']
        cls.sync.push(cls.vault)                                # objects on server

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _wired_cli(self):
        cli = CLI__Diff()
        cli.vault_ref   = CLI__Vault(api=self.api, token_store=CLI__Token_Store())
        cli.token_store = cli.vault_ref.token_store
        # Force the gate open: bypass URL plumbing in tests.
        cli._on_demand_api = lambda d, a: self.api
        return cli

    def _obj_path(self, oid):
        return os.path.join(self.vault, '.sg_vault', 'bare', 'data', oid)

    def test_cmd_show_recovers_via_on_demand_fetch(self, capsys):
        target = self._obj_path(self.commit_b)
        assert os.path.isfile(target)
        os.remove(target)                                       # simulate missing object

        args = types.SimpleNamespace(commit_id=self.commit_b, directory=self.vault,
                                     files_only=False, remote=None, base_url=None,
                                     verify_tls=None, token=None)
        self._wired_cli().cmd_show(args)
        out = capsys.readouterr().out
        assert self.commit_b[:20] in out                        # show rendered after retry
        assert os.path.isfile(target)                           # object re-downloaded

    def test_cmd_diff_recovers_via_on_demand_fetch(self, capsys):
        # restore B (other tests may have removed it) and remove A instead
        Vault__Diff(crypto=self.crypto, api=self.api).ensure_commit_local(
            self.vault, self.commit_b)
        target = self._obj_path(self.commit_a)
        if os.path.isfile(target):
            os.remove(target)

        args = types.SimpleNamespace(directory=self.vault, remote=False,
                                     commit=self.commit_a, commit2=self.commit_b,
                                     files_only=True, json_out=False, range_spec='',
                                     base_url=None, verify_tls=None, token=None)
        self._wired_cli().cmd_diff(args)
        capsys.readouterr()                                     # consume output


# ---------------------------------------------------------------------------
# F5 — A4 missing-base fallback (CLI__Merge._show_conflicts catches sparse base)
# ---------------------------------------------------------------------------

class Test_CLI__Merge__Resolve_Show__Fallback:

    @classmethod
    def setup_class(cls):
        cls.crypto = Vault__Crypto()
        cls.api    = Vault__API__In_Memory(); cls.api.setup()
        cls.sync   = Vault__Sync(crypto=cls.crypto, api=cls.api)
        cls.tmp    = tempfile.mkdtemp(prefix='show_fallback_')
        cls.vault  = os.path.join(cls.tmp, 'v')
        cls.sync.init(cls.vault)
        with open(os.path.join(cls.vault, 'hot.txt'), 'w') as f:
            f.write('a\n')
        cls.head = cls.sync.commit(cls.vault, message='head')['commit_id']

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def teardown_method(self):
        Vault__Merge__State().delete(self.vault)

    def test_fallback_when_lca_objects_absent(self, capsys):
        # Stage merge with a deliberately-bogus lca_id so flatten/load_commit raise.
        # The architect's fallback must catch + degrade to the path list, not crash.
        mgr = Vault__Merge__State()
        # bogus lca shaped like a real obj id so Safe_Str accepts it
        bogus_lca = 'obj-cas-imm-' + 'f' * 64
        mgr.write(self.vault,
                  mgr.new_state(self.head, self.head, bogus_lca, ['hot.txt']))
        args = types.SimpleNamespace(show=True, all=False, ours=False, theirs=False,
                                     file=None, directory=self.vault)
        CLI__Merge(crypto=self.crypto, api=self.api).cmd_resolve(args)
        out = capsys.readouterr().out
        assert '3-way view unavailable' in out
        assert 'hot.txt' in out                                 # still listed via resolver.show
