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
        args   = parser.parse_args(['file', 'write', 'content/hero.md', './some-dir'])
        assert args.path == 'content/hero.md'
        assert args.directory == './some-dir'
        assert args.push is False
        assert args.json is False
        assert args.also == []

    def test_write_parser_push_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['file', 'write', 'hero.md', '.', '--push'])
        assert args.push is True

    def test_write_parser_also_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['file', 'write', 'hero.md', '.',
                                    '--also', 'instructions/home.json:/tmp/f.json'])
        assert len(args.also) == 1
        assert args.also[0] == 'instructions/home.json:/tmp/f.json'

    def test_write_parser_message_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['file', 'write', 'hero.md', '.', '--message', 'hero v2'])
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
        args   = parser.parse_args(['file', 'cat', 'content/hero.md', '.', '--id'])
        assert args.id is True

    def test_cat_parser_has_json_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['file', 'cat', 'content/hero.md', '.', '--json'])
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
        args   = parser.parse_args(['file', 'ls', '.', '--ids'])
        assert args.ids is True

    def test_ls_parser_has_json_flag(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['file', 'ls', '.', '--json'])
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


class Test_CLI__Ls_Ids_Functional:
    """AC-8: ls --ids shows blob IDs in the text output."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'doc.md': 'document content'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_ls_ids_shows_blob_id_in_output(self, capsys):
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
            ids       = True
            json      = False

        vault.cmd_ls(FakeArgs())
        out = capsys.readouterr().out
        assert 'obj-cas-imm-' in out

    def test_ls_no_ids_hides_blob_id(self, capsys):
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
            json      = False

        vault.cmd_ls(FakeArgs())
        out = capsys.readouterr().out
        assert 'obj-cas-imm-' not in out


class Test_CLI__Info_Keys:
    """AC-13 + AC-14: clone and info show read_key and write_key availability."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    def setup_method(self):
        self.env       = self._env.restore()
        self.directory = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def test_info_full_clone_shows_read_key(self, capsys):
        """AC-14: info on a full clone prints the read_key."""
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            directory = self.directory
            token     = None
            base_url  = None

        vault.cmd_info(FakeArgs())
        out = capsys.readouterr().out
        assert 'Read key:' in out

    def test_info_full_clone_shows_write_key_available(self, capsys):
        """AC-14: info on a full clone shows write key is available."""
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            directory = self.directory
            token     = None
            base_url  = None

        vault.cmd_info(FakeArgs())
        out = capsys.readouterr().out
        assert 'Write key:' in out
        assert '✓ available' in out

    def test_info_read_only_clone_shows_write_key_not_available(self, capsys, tmp_path):
        """AC-14: info on a read-only clone shows write key is NOT available."""
        import json
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        from sgit_ai.sync.Vault__Storage     import Vault__Storage

        d = str(tmp_path / 'ro_vault')
        os.makedirs(os.path.join(d, '.sg_vault', 'local'), exist_ok=True)
        mode_path = Vault__Storage().clone_mode_path(d)
        with open(mode_path, 'w') as f:
            json.dump({'mode': 'read-only', 'vault_id': 'testvlt01',
                       'read_key': 'aa' * 32}, f)

        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            directory = d
            token     = None
            base_url  = None

        vault.cmd_info(FakeArgs())
        out = capsys.readouterr().out
        assert 'Write key:' in out
        assert 'not available' in out


class Test_CLI__ReadOnly__AC18_ExactMessage:
    """AC-18: exact error message for write/commit/push on read-only clone."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault()

    def setup_method(self):
        import json as _json
        self.env       = self._env.restore()
        self.directory = self.env.vault_dir
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        mode_path = Vault__Storage().clone_mode_path(self.directory)
        with open(mode_path, 'w') as f:
            _json.dump({'mode': 'read-only', 'vault_id': 'x', 'read_key': 'aa'}, f)

    def teardown_method(self):
        self.env.cleanup()

    def _vault(self):
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        import pytest
        return CLI__Vault(token_store=CLI__Token_Store(),
                          credential_store=CLI__Credential_Store())

    def test_exact_error_message_matches_ac18(self):
        import pytest
        vault = self._vault()
        with pytest.raises(RuntimeError) as exc_info:
            vault._check_read_only(self.directory)
        assert str(exc_info.value) == ('This vault was cloned read-only. '
                                       'To write, re-clone with the full vault key.')

    def test_commit_blocked_with_exact_message(self):
        import pytest
        vault = self._vault()

        class FakeArgs:
            directory = self.directory
            message   = ''
            token     = None
            base_url  = None

        with pytest.raises(RuntimeError, match='This vault was cloned read-only'):
            vault._check_read_only(FakeArgs().directory)


class Test_CLI__DeriveKeys__ReadOnly:
    """AC-19: derive-keys on read_key:vault_id input."""

    def test_derive_keys_read_key_format_outputs_limited_info(self, capsys):
        """AC-19: read_key:vault_id format outputs only vault_id and read_key."""
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto

        crypto   = Vault__Crypto()
        keys     = crypto.derive_keys('passphrase', 'myvlt01')
        read_key = keys['read_key']        # 64-char hex

        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            vault_key = f'{read_key}:myvlt01'

        vault.cmd_derive_keys(FakeArgs())
        out = capsys.readouterr().out
        assert 'vault_id:' in out
        assert 'read_key:' in out
        assert 'myvlt01' in out
        assert 'write_key' not in out.splitlines()[0]  # write_key not in main output
        assert 'not derivable' in out or 'Note:' in out

    def test_derive_keys_read_key_format_omits_write_key(self, capsys):
        """AC-19: write_key, ref_file_id, branch_index_file_id not shown for read_key input."""
        from sgit_ai.cli.CLI__Vault          import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.cli.CLI__Credential_Store import CLI__Credential_Store
        from sgit_ai.crypto.Vault__Crypto    import Vault__Crypto

        crypto   = Vault__Crypto()
        keys     = crypto.derive_keys('passphrase2', 'myvlt02')

        vault = CLI__Vault(token_store=CLI__Token_Store(),
                           credential_store=CLI__Credential_Store())

        class FakeArgs:
            vault_key = f'{keys["read_key"]}:myvlt02'

        vault.cmd_derive_keys(FakeArgs())
        out = capsys.readouterr().out
        lines = out.splitlines()
        key_lines = [l for l in lines if ':' in l and not l.startswith('Note') and not l.startswith(' ')]
        field_names = {l.split(':')[0].strip() for l in key_lines}
        assert 'write_key' not in field_names
        assert 'ref_file_id' not in field_names
        assert 'branch_index_file_id' not in field_names
