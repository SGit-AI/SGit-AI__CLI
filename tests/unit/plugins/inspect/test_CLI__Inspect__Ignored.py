import os
import sys
import shutil
import tempfile
from types import SimpleNamespace

import pytest

from sgit_ai.cli.CLI__Vault import CLI__Vault


class Test_CLI__Inspect__Ignored:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _args(self, rules=False, why=None):
        return SimpleNamespace(directory=self.tmp_dir, rules=rules, why=why)

    def _write(self, rel_path: str, content: str = 'x'):
        full = os.path.join(self.tmp_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)

    def _mkdir(self, rel_path: str):
        os.makedirs(os.path.join(self.tmp_dir, rel_path), exist_ok=True)

    # 1. Default mode lists all ignored items, tracked items omitted
    def test_inspect_ignored_default_lists_ignored_paths(self, capsys):
        self._mkdir('.git')
        self._mkdir('.venv')
        self._write('.env', 'SECRET=x')
        self._mkdir('dist')
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write('dist/\n')
        self._write('.claude/notes.md', '# hi')

        args = self._args()
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out

        assert '.git' in out
        assert '.venv' in out
        assert '.env' in out
        assert 'dist' in out
        assert '.claude' not in out.split('Ignored')[1]  # not in ignored section

    # 2. Default mode groups by reason
    def test_inspect_ignored_groups_by_reason_code(self, capsys):
        self._mkdir('.git')
        self._write('.env')
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write('build/\n')
        self._mkdir('build')

        args = self._args()
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out

        assert 'Hardcoded dirs' in out
        assert 'Hardcoded files' in out or 'env-secret' in out
        assert '.gitignore' in out

    # 3. --rules prints both hardcoded sets
    def test_inspect_ignored_rules_prints_sets(self, capsys):
        args = self._args(rules=True)
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out

        assert 'ALWAYS_IGNORED_DIRS' in out
        assert 'ALWAYS_IGNORED_FILES' in out
        assert '.sg_vault' in out
        assert '.env' in out

    # 4. --rules includes gitignore patterns
    def test_inspect_ignored_rules_prints_gitignore_patterns(self, capsys):
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write('dist/\n*.log\n')

        args = self._args(rules=True)
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out

        assert 'dist' in out
        assert '*.log' in out or 'log' in out

    # 5. --why tracked file
    def test_inspect_ignored_why_tracked_file(self, capsys):
        self._write('src/app.py', 'print("hi")')
        args = self._args(why='src/app.py')
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        assert 'TRACKED' in out

    # 6. --why file in ALWAYS_IGNORED_FILES
    def test_inspect_ignored_why_ignored_by_set(self, capsys):
        self._write('.env', 'SECRET=x')
        args = self._args(why='.env')
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        assert 'IGNORED' in out
        assert 'always_ignored_file' in out or '.env' in out

    # 7. --why file under a .gitignore-matched dir
    def test_inspect_ignored_why_ignored_by_pattern(self, capsys):
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write('dist/\n')
        self._write('dist/foo.js', 'built')
        args = self._args(why='dist/foo.js')
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        assert 'IGNORED' in out

    # 8. --why nonexistent path exits 1
    def test_inspect_ignored_why_with_nonexistent_path(self, capsys):
        args = self._args(why='some/nonexistent/file.txt')
        with pytest.raises(SystemExit) as exc_info:
            self.cli_vault.cmd_inspect_ignored(args)
        assert exc_info.value.code == 1

    # Totals line is present in default mode
    def test_inspect_ignored_shows_totals(self, capsys):
        self._write('app.py')
        self._mkdir('.git')
        args = self._args()
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        assert 'Total:' in out

    # env-secret glob shown correctly
    def test_inspect_ignored_env_secret_shown(self, capsys):
        self._write('.env.staging', 'SECRET=x')
        args = self._args()
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        assert '.env.staging' in out

    # env template is tracked, not ignored
    def test_inspect_ignored_env_template_tracked(self, capsys):
        self._write('.env.example', 'VAR=value')
        args = self._args()
        self.cli_vault.cmd_inspect_ignored(args)
        out = capsys.readouterr().out
        # .env.example should appear in tracked count, not ignored section
        assert '.env.example' not in out.split('Total:')[0].replace('Ignored in', '')
