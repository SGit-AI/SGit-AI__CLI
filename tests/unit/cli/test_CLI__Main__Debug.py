import os
import tempfile
import shutil
from sg_send_cli.cli.CLI__Main import CLI__Main


class Test_CLI__Main__Debug:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.local_dir = os.path.join(self.tmp_dir, '.sg_vault', 'local')
        os.makedirs(self.local_dir, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_and_load_debug_flag_on(self):
        cli = CLI__Main()
        cli._save_debug_flag(self.tmp_dir, True)
        assert cli._load_debug_flag(self.tmp_dir) is True

    def test_save_and_load_debug_flag_off(self):
        cli = CLI__Main()
        cli._save_debug_flag(self.tmp_dir, False)
        assert cli._load_debug_flag(self.tmp_dir) is False

    def test_load_debug_flag_missing_file(self):
        cli = CLI__Main()
        assert cli._load_debug_flag(self.tmp_dir) is False

    def test_load_debug_flag_missing_directory(self):
        cli = CLI__Main()
        assert cli._load_debug_flag('/nonexistent/path') is False

    def test_save_debug_flag_no_vault_dir(self):
        cli = CLI__Main()
        try:
            cli._save_debug_flag('/tmp/no-vault-here', True)
            assert False, 'Should have raised RuntimeError'
        except RuntimeError:
            pass

    def test_setup_debug_with_none_directory(self):
        """Regression: clone command sets directory=None which caused TypeError in os.path.join."""
        cli  = CLI__Main()
        args = type('Args', (), {'directory': None, 'debug': False})()
        result = cli._setup_debug(args)
        assert result is None                                           # no crash, no debug log

    def test_setup_debug_with_missing_directory_attr(self):
        """Commands that don't define a directory arg should also work."""
        cli  = CLI__Main()
        args = type('Args', (), {'debug': False})()
        result = cli._setup_debug(args)
        assert result is None
