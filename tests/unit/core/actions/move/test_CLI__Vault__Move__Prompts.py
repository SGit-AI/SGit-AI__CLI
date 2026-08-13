import os
import sys
import types

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


def _run_move(env, prompts, **arg_overrides):
    cli  = CLI__Vault(token_store=CLI__Token_Store())
    cli.api = env.api
    cli.move_countdown_secs = 0
    cli.move_prompt_answers = list(prompts)
    args = _args(directory=env.vault_dir, **arg_overrides)
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

    def test_all_yes_completes_move(self):
        old_id = _vault_id(self.env)
        _run_move(self.env, ALL_YES)
        assert _vault_id(self.env) != old_id

    def test_no_at_step_1_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    def test_no_at_step_2_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    def test_no_at_step_3_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    def test_no_at_step_4_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    def test_no_at_step_5_aborts(self):
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key

    def test_no_at_step_6_aborts(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        _run_move(self.env, ['y', 'y', 'y', 'y', 'y', 'n'])
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    def test_edit_at_step_1_uses_explicit_key(self):
        explicit = 'myphraseexplicit123456:expl0001'
        _run_move(self.env, ['edit', explicit, 'y', 'y', 'y', 'y', 'y'])
        assert _vault_key(self.env) == explicit

    def test_different_at_step_4_uses_custom_url(self):
        old_id = _vault_id(self.env)
        from sgit_ai.network.api.Vault__API import DEFAULT_BASE_URL
        _run_move(self.env, ['y', 'y', 'y', 'different', DEFAULT_BASE_URL, 'y', 'y'])
        assert _vault_id(self.env) != old_id

    def test_yes_flag_skips_all_prompts(self):
        old_id = _vault_id(self.env)
        cli = CLI__Vault(token_store=CLI__Token_Store())
        cli.api = self.env.api
        cli.cmd_vault_move(_args(directory=self.env.vault_dir, yes=True))
        assert _vault_id(self.env) != old_id

    def test_dry_run_yes_no_state_change(self):
        old_id  = _vault_id(self.env)
        old_key = self.env.vault_key
        cli = CLI__Vault(token_store=CLI__Token_Store())
        cli.api = self.env.api
        cli.cmd_vault_move(_args(directory=self.env.vault_dir, yes=True, dry_run=True))
        assert _vault_key(self.env) == old_key
        assert not self.env.api.is_tombstoned(old_id)

    def test_none_response_aborts_cleanly(self):
        old_key = self.env.vault_key
        _run_move(self.env, [None])
        assert _vault_key(self.env) == old_key
