"""Unit tests for CLI__Migrate — `sgit migrate plan | apply [--force] | status`.

Driven through CLI__Main's real parser from inside a real vault (Vault__Test_Env). The one
registered migration (tree-iv-determinism) is already applied on any vault this sgit
creates, so the pending case is produced by re-encrypting the trees with random IVs, the
way the migration's own tests do."""
import os

import pytest

from sgit_ai.cli.CLI__Main                                       import CLI__Main
from sgit_ai.migrations.Migration__Runner                        import MIGRATIONS_FILE
from tests._helpers.vault_test_env                               import Vault__Test_Env
from tests.unit.migrations.test_Migration__Tree_IV_Determinism   import _corrupt_trees_to_random_iv


class Test_CLI__Migrate:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': b'hello', 'src/main.py': b'print("hello")'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env      = self._env.restore()
        self.vault    = self.env.vault_dir
        self.sg_dir   = os.path.join(self.vault, '.sg_vault')
        keys          = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        self.read_key = bytes.fromhex(keys['read_key'])
        self.cli      = CLI__Main()
        with open(os.path.join(self.sg_dir, 'local', 'base_url'), 'w') as f:   # a vault that records its server:
            f.write('http://127.0.0.1:9')                                       # one that records none refuses (S1)

    def teardown_method(self):
        self.env.cleanup()

    def _make_pending(self):
        pairs = _corrupt_trees_to_random_iv(self.sg_dir, self.read_key)
        assert pairs, 'the vault must have trees to re-encrypt'

    # ── plan ────────────────────────────────────────────────────────────
    def test_plan_on_an_up_to_date_vault(self, monkeypatch, capsys):
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'plan'])
        assert capsys.readouterr().out == 'No pending migrations.\n'

    def test_plan_lists_the_pending_migration(self, monkeypatch, capsys):
        self._make_pending()
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'plan'])
        assert capsys.readouterr().out == 'Pending migrations:\n  - tree-iv-determinism\n'

    def test_plan_accepts_an_explicit_directory(self, monkeypatch, capsys):
        monkeypatch.chdir(os.path.dirname(self.vault))
        with pytest.raises(SystemExit):                     # migrate is inside-only: cwd is not a vault
            self.cli.run(['migrate', 'plan'])
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'plan', self.vault])
        assert capsys.readouterr().out.endswith('No pending migrations.\n')

    # ── status ──────────────────────────────────────────────────────────
    def test_status_with_no_record(self, monkeypatch, capsys):
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'status'])
        assert capsys.readouterr().out == 'No migrations applied.\n'

    # ── apply ───────────────────────────────────────────────────────────
    def test_apply_on_an_up_to_date_vault_does_nothing(self, monkeypatch, capsys):
        """Signed commits do not block a no-op: nothing pending means nothing is rewritten."""
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'apply', '--force'])
        assert capsys.readouterr().out == 'Nothing to migrate — vault is already up to date.\n'
        assert not os.path.isfile(os.path.join(self.sg_dir, MIGRATIONS_FILE))

    def test_apply_refuses_a_vault_with_signed_commits_unless_forced(self, monkeypatch, capsys):
        """Every commit this sgit makes is signed, so a plain apply exits 2 with the rewrite
        warning and touches nothing — even when the vault is up to date (the guard runs first)."""
        monkeypatch.chdir(self.vault)
        with pytest.raises(SystemExit) as exc:
            self.cli.run(['migrate', 'apply'])
        assert exc.value.code == 2
        out = capsys.readouterr()
        assert out.out == ''
        assert out.err.splitlines()[0].startswith('error: this vault has signed commits; a migration rewrites history')
        assert out.err.splitlines()[1] == '  Re-run with --force to proceed anyway (other clones will need sgit pull --accept-rewind).'

    def test_apply_with_force_runs_the_migration_and_records_it(self, monkeypatch, capsys):
        self._make_pending()
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'apply', '--force'])
        assert capsys.readouterr().out == 'Applied: tree-iv-determinism\n'
        self.cli.run(['migrate', 'status'])
        line = capsys.readouterr().out.rstrip()
        assert line.startswith('  tree-iv-determinism  applied=')
        assert '  trees=' in line and '  commits=' in line
        trees = int(line.split('trees=')[1].split()[0])
        assert trees > 0
        self.cli.run(['migrate', 'plan'])
        assert capsys.readouterr().out == 'No pending migrations.\n'

    def test_second_apply_is_a_no_op_once_recorded(self, monkeypatch, capsys):
        self._make_pending()
        monkeypatch.chdir(self.vault)
        self.cli.run(['migrate', 'apply', '--force'])
        capsys.readouterr()
        self.cli.run(['migrate', 'apply', '--force'])
        assert capsys.readouterr().out == 'Nothing to migrate — vault is already up to date.\n'

    def test_migrate_without_a_subcommand_prints_help(self, monkeypatch, capsys):
        monkeypatch.chdir(self.vault)
        try:
            self.cli.run(['migrate'])
        except SystemExit:
            pass
        assert 'plan' in capsys.readouterr().out
