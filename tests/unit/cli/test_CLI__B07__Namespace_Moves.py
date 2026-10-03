"""Tests for B07 CLI namespace moves — new namespace paths are correctly routed."""
import pytest
from sgit_ai.cli.CLI__Main             import CLI__Main
from sgit_ai.cli.CLI__Stash            import CLI__Stash


def _build():
    cli = CLI__Main()
    return cli, cli.build_parser()


# ---------------------------------------------------------------------------
# New paths — parser routes to correct handler
# ---------------------------------------------------------------------------

class Test_B07__New_Namespace_Paths:

    def test_vault_stash_routes_to_cmd_stash(self):
        _, p = _build()
        args = p.parse_args(['vault', 'stash'])
        assert args.func.__self__.__class__ is CLI__Stash

    def test_vault_stash_pop_routes_correctly(self):
        _, p = _build()
        args = p.parse_args(['vault', 'stash', 'pop'])
        assert args.func.__self__.__class__ is CLI__Stash
        assert args.func.__func__ is CLI__Stash.cmd_stash_pop

    def test_vault_stash_list_routes_correctly(self):
        _, p = _build()
        args = p.parse_args(['vault', 'stash', 'list'])
        assert args.func.__self__.__class__ is CLI__Stash
        assert args.func.__func__ is CLI__Stash.cmd_stash_list

    def test_vault_stash_drop_routes_correctly(self):
        _, p = _build()
        args = p.parse_args(['vault', 'stash', 'drop'])
        assert args.func.__self__.__class__ is CLI__Stash
        assert args.func.__func__ is CLI__Stash.cmd_stash_drop

    def test_vault_namespace_has_stash_remote(self):
        _, p = _build()
        vault_sub = p._subparsers._group_actions[0].choices['vault']
        vault_choices = vault_sub._subparsers._group_actions[0].choices
        assert 'stash'  in vault_choices
        assert 'remote' in vault_choices

    def test_share_namespace_removed(self):
        # The SG/Send share/transfer namespace was removed with the Simple Token feature.
        _, p = _build()
        assert 'share' not in p._subparsers._group_actions[0].choices


# ---------------------------------------------------------------------------
# Old top-level aliases are removed — not registered as subparsers
# ---------------------------------------------------------------------------

class Test_B07__Aliases_Removed:

    def _top_level_choices(self):
        _, p = _build()
        return set(p._subparsers._group_actions[0].choices.keys())

    def test_old_stash_not_a_top_level_command(self):
        assert 'stash' not in self._top_level_choices()

    def test_old_send_not_a_top_level_command(self):
        assert 'send' not in self._top_level_choices()

    def test_old_receive_not_a_top_level_command(self):
        assert 'receive' not in self._top_level_choices()

    def test_publish_is_static_publishing_not_the_old_share(self):
        # The Simple-Token share `publish` was removed (B07); decision 9 of the
        # static-publishing pack reintroduces `sgit publish` as the plaintext-
        # surface generator. Assert it exists AND is not the old share verb.
        assert 'publish' in self._top_level_choices()
        parser = CLI__Main().build_parser()
        args   = parser.parse_args(['publish', '--visibility', 'public', '--yes'])
        assert args.command == 'publish'
        assert not hasattr(args, 'token_receiver')       # nothing of the old share surface

    def test_old_export_not_a_top_level_command(self):
        assert 'export' not in self._top_level_choices()

    def test_remote_is_top_level_alias_of_vault_remote(self):
        # `sgit remote ...` was re-introduced as a top-level alias for
        # `sgit vault remote ...` to make multi-remote management ergonomic
        # (set-url, set-default, add, list). The B07 policy of "no aliases"
        # has a documented exception for `remote` because it's a primary
        # daily-use surface alongside push/pull.
        assert 'remote' in self._top_level_choices()


# ---------------------------------------------------------------------------
# Top-level count guard
# ---------------------------------------------------------------------------

class Test_B07__Top_Level_Count:

    def test_real_top_level_commands_within_limit(self):
        cli = CLI__Main()
        p   = cli.build_parser()
        all_choices = set(p._subparsers._group_actions[0].choices.keys())
        # Limit was 30; bumped to 32 when `remote` was re-added as a top-level
        # alias for `vault remote` (multi-remote UX). Keep this guard tight so
        # new commands have to argue for top-level placement.
        assert len(all_choices) <= 32, f'Too many top-level commands: {sorted(all_choices)}'
