"""`sgit --vault PATH <command>` works on PATH (cli.build, review of 0.26.10): it used to steer only the
inside/outside check, so `sgit --vault P check fsck` checked the current folder."""
import os
import tempfile

from sgit_ai.cli.CLI__Main          import CLI__Main
from tests._helpers.vault_test_env  import Vault__Test_Env


class Test_CLI__Main__Vault_Override:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'a\n'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.away = tempfile.mkdtemp()

    def teardown_method(self):
        self.env.cleanup()

    def sgit(self, capsys, *argv) -> tuple:
        here = os.getcwd()
        os.chdir(self.away)
        code = 0
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9'] + list(argv))
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.chdir(here)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def test_check_fsck_and_status_work_on_the_named_vault(self, capsys):
        code, out, _ = self.sgit(capsys, '--vault', self.env.vault_dir, 'check', 'fsck')
        assert code == 0 and f'Checking vault integrity in {self.env.vault_dir}' in out and 'Vault OK.' in out
        code, out, _ = self.sgit(capsys, '--vault', self.env.vault_dir, 'status')
        assert code == 0 and 'Nothing to commit' in out

    def test_an_explicit_directory_still_wins_and_clone_keeps_its_target(self):
        cli  = CLI__Main()
        args = cli.build_parser().parse_args(['--vault', '/somewhere', 'check', 'fsck', '/elsewhere'])
        cli._apply_vault_override(args)
        assert args.directory == '/elsewhere'
        args = cli.build_parser().parse_args(['--vault', '/somewhere', 'clone', 'key', 'target'])
        cli._apply_vault_override(args)
        assert getattr(args, 'directory', None) != '/somewhere'
