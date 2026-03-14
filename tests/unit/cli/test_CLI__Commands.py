import os
import sys
import tempfile
import shutil
import pytest
from types         import SimpleNamespace

from sg_send_cli.crypto.Vault__Crypto     import Vault__Crypto
from sg_send_cli.sync.Vault__Sync         import Vault__Sync
from sg_send_cli.cli.CLI__Token_Store     import CLI__Token_Store
from sg_send_cli.cli.CLI__Vault           import CLI__Vault
from sg_send_cli.cli.CLI__Main            import CLI__Main
from sg_send_cli.cli                      import main
from sg_send_cli.api.Vault__API           import Vault__API


class Test_CLI__Token_Store:

    def setup_method(self):
        self.tmp_dir     = tempfile.mkdtemp()
        self.sg_dir      = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(self.sg_dir)
        self.token_store = CLI__Token_Store()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_and_load_token(self):
        self.token_store.save_token('my-token-123', self.tmp_dir)
        assert self.token_store.load_token(self.tmp_dir) == 'my-token-123'

    def test_load_token_returns_empty_when_no_file(self):
        assert self.token_store.load_token(self.tmp_dir) == ''

    def test_resolve_token_saves_and_returns_when_given(self):
        result = self.token_store.resolve_token('tok-abc', self.tmp_dir)
        assert result == 'tok-abc'
        assert self.token_store.load_token(self.tmp_dir) == 'tok-abc'

    def test_resolve_token_loads_from_file_when_empty(self):
        self.token_store.save_token('tok-saved', self.tmp_dir)
        result = self.token_store.resolve_token('', self.tmp_dir)
        assert result == 'tok-saved'

    def test_resolve_token_loads_from_file_when_none(self):
        self.token_store.save_token('tok-saved', self.tmp_dir)
        result = self.token_store.resolve_token(None, self.tmp_dir)
        assert result == 'tok-saved'

    def test_load_vault_key_reads_from_file(self):
        local_dir = os.path.join(self.sg_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'vault_key'), 'w') as f:
            f.write('passphrase:vault-id-123')
        assert self.token_store.load_vault_key(self.tmp_dir) == 'passphrase:vault-id-123'

    def test_load_vault_key_returns_empty_when_missing(self):
        assert self.token_store.load_vault_key(self.tmp_dir) == ''

    def test_resolve_read_key_from_vault_key_arg(self):
        args = SimpleNamespace(vault_key='passphrase:vault-id', directory=self.tmp_dir)
        key  = self.token_store.resolve_read_key(args)
        assert key is not None
        assert isinstance(key, bytes)

    def test_resolve_read_key_from_vault_file(self):
        local_dir = os.path.join(self.sg_dir, 'local')
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, 'vault_key'), 'w') as f:
            f.write('passphrase:vault-id')
        args = SimpleNamespace(vault_key=None, directory=self.tmp_dir)
        key  = self.token_store.resolve_read_key(args)
        assert key is not None

    def test_resolve_read_key_returns_none_when_missing(self):
        args = SimpleNamespace(vault_key=None, directory=self.tmp_dir)
        key  = self.token_store.resolve_read_key(args)
        assert key is None


class Test_CLI__Vault_Init:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_init_requires_token(self):
        args = SimpleNamespace(token=None, base_url=None, directory=self.tmp_dir)
        with pytest.raises(SystemExit) as exc_info:
            self.cli_vault.cmd_init(args)
        assert exc_info.value.code == 1

    def test_init_creates_vault(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'my-vault')
        args = SimpleNamespace(token='test-token', base_url='http://localhost:99999',
                               directory=vault_dir, vault_key=None)
        self.cli_vault.cmd_init(args)
        output = capsys.readouterr().out
        assert 'Initialized empty vault' in output
        assert 'Vault ID:'              in output
        assert 'Vault key:'             in output
        assert 'Branch:'                in output


class Test_CLI__Vault_Commit:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_commit_after_adding_file(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'file.txt'), 'w') as f:
            f.write('content')
        args = SimpleNamespace(directory=vault_dir, message='test commit')
        self.cli_vault.cmd_commit(args)
        output = capsys.readouterr().out
        assert 'commit' in output.lower()


class Test_CLI__Vault_Status:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_status_clean_vault(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        args = SimpleNamespace(directory=vault_dir)
        self.cli_vault.cmd_status(args)
        output = capsys.readouterr().out
        assert 'clean' in output.lower()

    def test_status_with_added_file(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        with open(os.path.join(vault_dir, 'new-file.txt'), 'w') as f:
            f.write('hello')
        args = SimpleNamespace(directory=vault_dir)
        self.cli_vault.cmd_status(args)
        output = capsys.readouterr().out
        assert 'new-file.txt' in output


class Test_CLI__Vault_Branches:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_branches_lists_both_branches(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        args = SimpleNamespace(directory=vault_dir)
        self.cli_vault.cmd_branches(args)
        output = capsys.readouterr().out
        assert 'current' in output
        assert 'local' in output
        assert '*' in output


class Test_CLI__Vault_Push_Pull:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_push_nothing_to_push(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        self.cli_vault.token_store.save_token('tok', vault_dir)
        args = SimpleNamespace(token='tok', base_url=None, directory=vault_dir)
        self.cli_vault.cmd_push(args)
        output = capsys.readouterr().out
        assert 'Nothing to push' in output

    def test_pull_up_to_date(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        self.cli_vault.token_store.save_token('tok', vault_dir)
        args = SimpleNamespace(token='tok', base_url=None, directory=vault_dir)
        self.cli_vault.cmd_pull(args)
        output = capsys.readouterr().out
        assert 'up to date' in output.lower()


class Test_CLI__Vault_Derive_Keys:

    def test_derive_keys_prints_all_fields(self, capsys):
        cli_vault = CLI__Vault()
        args      = SimpleNamespace(vault_key='test-passphrase:test-vault-id')
        cli_vault.cmd_derive_keys(args)
        output = capsys.readouterr().out
        assert 'vault_id:'         in output
        assert 'read_key:'         in output
        assert 'write_key:'        in output
        assert 'tree_file_id:'     in output
        assert 'settings_file_id:' in output
        assert 'ref_file_id:'      in output


class Test_CLI__Vault_Inspect:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_inspect_shows_vault_info(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        args = SimpleNamespace(directory=vault_dir)
        self.cli_vault.cmd_inspect(args)
        output = capsys.readouterr().out
        assert len(output) > 0

    def test_inspect_stats(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        args = SimpleNamespace(directory=vault_dir)
        self.cli_vault.cmd_inspect_stats(args)
        output = capsys.readouterr().out
        assert 'Object Store Stats' in output
        assert 'Total objects' in output


class Test_CLI__Vault_Inspect_Tree:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_inspect_tree_shows_entries(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        with open(os.path.join(vault_dir, 'data.txt'), 'w') as f:
            f.write('some data')
        self.sync.commit(vault_dir)

        args = SimpleNamespace(directory=vault_dir, vault_key=vault_key)
        self.cli_vault.cmd_inspect_tree(args)
        output = capsys.readouterr().out
        assert 'data.txt' in output


class Test_CLI__Vault_Inspect_Log:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_inspect_log_shows_commits(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        args = SimpleNamespace(directory=vault_dir, vault_key=vault_key, oneline=False, graph=False)
        self.cli_vault.cmd_inspect_log(args)
        output = capsys.readouterr().out
        assert len(output) > 0

    def test_inspect_log_oneline(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        args = SimpleNamespace(directory=vault_dir, vault_key=vault_key, oneline=True, graph=False)
        self.cli_vault.cmd_inspect_log(args)
        output = capsys.readouterr().out
        assert len(output) > 0


class Test_CLI__Vault_Cat_Object:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cat_object_no_key_exits(self):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        self.sync.init(vault_dir)
        os.remove(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key'))
        args = SimpleNamespace(directory=vault_dir, object_id='aabbccddeeff', vault_key=None)
        with pytest.raises(SystemExit) as exc_info:
            self.cli_vault.cmd_cat_object(args)
        assert exc_info.value.code == 1


class Test_CLI__Vault_Log:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.cli_vault = CLI__Vault()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_log_delegates_to_inspect_log(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        args = SimpleNamespace(directory=vault_dir, vault_key=vault_key, oneline=False, graph=False)
        self.cli_vault.cmd_log(args)
        output = capsys.readouterr().out
        assert len(output) > 0

    def test_log_oneline(self, capsys):
        vault_dir = os.path.join(self.tmp_dir, 'vault')
        result    = self.sync.init(vault_dir)
        vault_key = result['vault_key']

        args = SimpleNamespace(directory=vault_dir, vault_key=vault_key, oneline=True, graph=False)
        self.cli_vault.cmd_log(args)
        output = capsys.readouterr().out
        assert len(output) > 0


class Test_CLI__Main_Parser:

    def test_no_command_exits(self):
        cli_main = CLI__Main()
        with pytest.raises(SystemExit) as exc_info:
            cli_main.run([])
        assert exc_info.value.code == 1

    def test_help_flag(self):
        cli_main = CLI__Main()
        with pytest.raises(SystemExit) as exc_info:
            cli_main.run(['--help'])
        assert exc_info.value.code == 0

    def test_version_flag(self):
        cli_main = CLI__Main()
        with pytest.raises(SystemExit) as exc_info:
            cli_main.run(['--version'])
        assert exc_info.value.code == 0

    def test_main_entry_point(self):
        original_argv = sys.argv
        try:
            sys.argv = ['sg-send-cli']
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        finally:
            sys.argv = original_argv

    def test_log_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['log', '--oneline', '.'])
        assert args.command == 'log'
        assert args.oneline is True

    def test_commit_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['commit', '-m', 'test message', '.'])
        assert args.command == 'commit'
        assert args.message == 'test message'

    def test_branches_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['branches', '.'])
        assert args.command == 'branches'

    def test_merge_abort_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['merge-abort', '.'])
        assert args.command == 'merge-abort'

    def test_status_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['status', '.'])
        assert args.command == 'status'
