"""Tests for Vault__Sync.probe_token() — token type identification without cloning."""
import json

import pytest

SIMPLE_VAULT_TOKEN = 'give-foul-8361'


class Test_Vault__Sync__Probe:
    """probe_token on a real in-memory vault — vault path."""

    @pytest.fixture(autouse=True)
    def _setup(self, probe_vault_env):
        # F5: shared session-scope env; restore() returns isolated copy.
        self.env  = probe_vault_env.restore()
        self.sync = self.env.sync
        yield
        self.env.cleanup()

    def test_probe_vault_token_returns_vault_type(self):
        result = self.sync.probe_token(self.env.vault_key)
        assert result['type'] == 'vault'

    def test_probe_vault_token_includes_vault_id(self):
        result = self.sync.probe_token(self.env.vault_key)
        assert 'vault_id' in result
        assert result['vault_id']

    def test_probe_vault_token_includes_token(self):
        result = self.sync.probe_token(self.env.vault_key)
        assert result['token'] == self.env.vault_key

    def test_probe_vault_token_strips_vault_prefix(self):
        result = self.sync.probe_token(f'vault://{self.env.vault_key}')
        assert result['type'] == 'vault'
        assert result['token'] == self.env.vault_key

    def test_probe_unknown_token_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='not found'):
            self.sync.probe_token('fake-word-0001')

    def test_probe_non_simple_token_raises(self):
        import pytest
        with pytest.raises(RuntimeError, match='simple tokens'):
            self.sync.probe_token('passphrase:vault_id_format')


class Test_Vault__Sync__Probe__Parser:
    """Test that the probe parser is correctly wired in CLI__Main."""

    def test_probe_parser_exists(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['probe', 'give-foul-8361'])
        assert args.token == 'give-foul-8361'
        assert args.json is False

    def test_probe_parser_json_flag(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['probe', 'give-foul-8361', '--json'])
        assert args.json is True

    def test_probe_not_in_no_walk_up(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert 'probe' in CLI__Main._NO_WALK_UP


class Test_Vault__Sync__Probe__JSON:
    """probe_token --json output is valid and complete."""

    @pytest.fixture(autouse=True)
    def _setup(self, probe_vault_env):
        # F5: same session-scope env; restore() returns isolated copy.
        self.env  = probe_vault_env.restore()
        self.sync = self.env.sync
        yield
        self.env.cleanup()

    def test_probe_vault_json_has_required_keys(self):
        result = self.sync.probe_token(self.env.vault_key)
        assert set(result.keys()) >= {'type', 'vault_id', 'token'}

    def test_probe_vault_json_serialisable(self):
        result     = self.sync.probe_token(self.env.vault_key)
        serialised = json.dumps(result)
        parsed     = json.loads(serialised)
        assert parsed['type'] == 'vault'
