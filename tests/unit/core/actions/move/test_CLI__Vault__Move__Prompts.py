"""CLI prompt-flow tests for `sgit vault move` — Brief 03 §3i."""
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '_helpers'))
from vault_test_env import Vault__Test_Env

from sgit_ai.cli.CLI__Vault             import CLI__Vault
from sgit_ai.cli.CLI__Token_Store       import CLI__Token_Store
from sgit_ai.core.Vault__Sync           import Vault__Sync
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto


def _args(**kwargs):
    defaults = dict(
        directory='.',
        new_key=None,
        to=None,
        reason='prompt-test',
        yes=False,
        dry_run=False,
        cleanup=False,
        token=None,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_cli(env):
    cli = CLI__Vault(token_store=CLI__Token_Store())
    # Patch the create_sync so status/etc. use in-memory API; cmd_vault_move
    # still constructs its own Vault__API() so we patch that separately.
    return cli


def _run_move(env, prompts, **arg_overrides):
    """Run cmd_vault_move with mocked prompts and the env's in-memory API."""
    cli  = _make_cli(env)
    args = _args(directory=env.vault_dir, **arg_overrides)

    prompt_iter = iter(prompts)

    # CLI__Input is imported at module level in CLI__Vault; patch it there.
    with patch('sgit_ai.cli.CLI__Vault.CLI__Input') as mock_input_cls, \
         patch('sgit_ai.network.api.Vault__API.Vault__API',
               return_value=env.api), \
         patch('time.sleep'):
        mock_instance = MagicMock()
        mock_input_cls.return_value = mock_instance
        mock_instance.prompt.side_effect = list(prompts)
        cli.cmd_vault_move(args)


def _vault_key(env):
    return open(os.path.join(env.vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()


def _vault_id(env):
    return env.crypto.derive_keys_from_vault_key(_vault_key(env))['vault_id']


ALL_YES = ['y', 'y', 'y', 'y', 'y', 'y']


class Test_CLI__Vault__Move__Prompts:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'item.txt': 'content'})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    # 1. All y → move completes; vault_id changes
    def test_all_yes_completes_move(self):
        old_id = _vault_id(self.env)
        _run_move(self.env, ALL_YES)
        assert _vault_id(self.env) != old_id

    # 2. N at step 1 → vault unchanged
    def test_no_at_step_1_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    # 3. N at step 2 → vault unchanged
    def test_no_at_step_2_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    # 4. N at step 3 → vault unchanged
    def test_no_at_step_3_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    # 5. N at step 4 → vault unchanged
    def test_no_at_step_4_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    # 6. N at step 5 → vault unchanged
    def test_no_at_step_5_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    # 7. N at step 6 → vault unchanged (old vault NOT tombstoned)
    def test_no_at_step_6_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    # 8. 'edit' at step 1 then explicit key → that key is used
    def test_edit_at_step_1_uses_explicit_key(self):
        explicit = 'myphraseexplicit123456:expl0001'
        _run_move(self.env, ['edit', explicit, 'y', 'y', 'y', 'y', 'y'])
        assert _vault_key(self.env) == explicit

    # 9. 'different' at step 4 then custom URL → move proceeds with that URL
    def test_different_at_step_4_uses_custom_url(self):
        old_id = _vault_id(self.env)
        from sgit_ai.network.api.Vault__API import DEFAULT_BASE_URL
        _run_move(self.env, ['y', 'y', 'y', 'different', DEFAULT_BASE_URL, 'y', 'y'])
        assert _vault_id(self.env) != old_id

    # 10. --yes flag skips all prompts; move completes
    def test_yes_flag_skips_all_prompts(self):
        old_id = _vault_id(self.env)
        with patch('sgit_ai.network.api.Vault__API.Vault__API',
                   return_value=self.env.api), \
             patch('time.sleep'):
            cli = _make_cli(self.env)
            cli.cmd_vault_move(_args(directory=self.env.vault_dir, yes=True))
        assert _vault_id(self.env) != old_id

    # 11. --dry-run with --yes → vault unchanged
    def test_dry_run_yes_no_state_change(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        with patch('sgit_ai.network.api.Vault__API.Vault__API',
                   return_value=self.env.api), \
             patch('time.sleep'):
            cli = _make_cli(self.env)
            cli.cmd_vault_move(_args(directory=self.env.vault_dir, yes=True, dry_run=True))
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    # 12. None response from any prompt → vault unchanged (cancelled)
    def test_none_response_aborts_cleanly(self):
        old_key = self.env.vault_key
        _run_move(self.env, [None])
        assert _vault_key(self.env) == old_key
