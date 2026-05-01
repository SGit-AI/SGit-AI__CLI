"""Tests for sgit write command and cat/ls extensions."""
import io
import json
import os
import sys
import shutil
import tempfile

from sgit_ai.cli.CLI__Main           import CLI__Main
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto
from sgit_ai.sync.Vault__Sync        import Vault__Sync
from tests.unit.sync.vault_test_env  import Vault__Test_Env


def _make_cli(api):
    from sgit_ai.cli.CLI__Vault          import CLI__Vault
    from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
    from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
    vault = CLI__Vault(token_store=CLI__Token_Store(),
                       credential_store=CLI__Credential_Store())
    vault.token_store = CLI__Token_Store()
    cli   = CLI__Main(vault=vault)
    return cli


class Test_CLI__Write_Parser:
    """Test that the write parser is correctly wired."""

    def test_write_parser_exists(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['write', 'content/hero.md', './some-dir'])
        assert args.path == 'content/hero.md'
        assert args.directory == './some-dir'
        assert args.push is False
        assert args.json is False
        assert args.also == []

    def test_write_parser_push_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['write', 'hero.md', '.', '--push'])
        assert args.push is True

    def test_write_parser_also_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['write', 'hero.md', '.',
                                    '--also', 'instructions/home.json:/tmp/f.json'])
        assert len(args.also) == 1
        assert args.also[0] == 'instructions/home.json:/tmp/f.json'

    def test_write_parser_message_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['write', 'hero.md', '.', '--message', 'hero v2'])
        assert args.message == 'hero v2'


class Test_CLI__Cat_Extensions:
    """Test --id and --json flags on sgit cat."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'content/hero.md': 'hero content'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_cat_parser_has_id_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['cat', 'content/hero.md', '.', '--id'])
        assert args.id is True

    def test_cat_parser_has_json_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['cat', 'content/hero.md', '.', '--json'])
        assert args.json is True

    def test_cat_id_prints_blob_id(self, capsys):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            path      = 'content/hero.md'
            directory = self.directory
            token     = None
            base_url  = None
            id        = True
            json      = False

        vault.cmd_cat(FakeArgs())
        captured = capsys.readouterr()
        assert captured.out.strip().startswith('obj-cas-imm-')

    def test_cat_json_outputs_valid_json(self, capsys):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            path      = 'content/hero.md'
            directory = self.directory
            token     = None
            base_url  = None
            id        = False
            json      = True

        vault.cmd_cat(FakeArgs())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['path'] == 'content/hero.md'
        assert data['blob_id'].startswith('obj-cas-imm-')
        assert isinstance(data['size'], int)
        assert 'content_type' in data
        assert isinstance(data['fetched'], bool)


class Test_CLI__Ls_Extensions:
    """Test --ids and --json flags on sgit ls."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'doc.md': 'doc', 'img/logo.png': 'png'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.sync      = self.env.sync
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_ls_parser_has_ids_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['ls', '.', '--ids'])
        assert args.ids is True

    def test_ls_parser_has_json_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['ls', '.', '--json'])
        assert args.json is True

    def test_ls_json_output_is_array(self, capsys):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            path      = None
            directory = self.directory
            token     = None
            base_url  = None
            ids       = False
            json      = True

        vault.cmd_ls(FakeArgs())
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 2
        for entry in data:
            assert 'path' in entry
            assert 'blob_id' in entry
            assert 'size' in entry
            assert 'fetched' in entry


class Test_CLI__Read_Only_Guard:
    """Test that commit and push are blocked in read-only clones."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        import json as _json
        self.env       = self._env.restore()
        self.directory = self.env.vault_dir
        # Write clone_mode.json to make vault read-only
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        storage    = Vault__Storage()
        mode_path  = storage.clone_mode_path(self.directory)
        with open(mode_path, 'w') as f:
            _json.dump({'mode': 'read-only', 'vault_id': 'x', 'read_key': 'aa'}, f)

    def teardown_method(self):
        self.env.cleanup()

    def test_cmd_write_blocked_in_read_only(self):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        import pytest
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            path      = 'hero.md'
            directory = self.directory
            token     = None
            base_url  = None
            json      = False
            message   = ''
            push      = False
            file      = None
            also      = []

        with pytest.raises(RuntimeError, match='read-only'):
            vault.cmd_write(FakeArgs())

    def test_check_read_only_raises(self):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        import pytest
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())
        with pytest.raises(RuntimeError, match='read-only'):
            vault._check_read_only(self.directory)
