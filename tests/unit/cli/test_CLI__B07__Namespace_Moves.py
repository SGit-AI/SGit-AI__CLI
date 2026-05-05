"""Tests for B07 CLI namespace moves — new namespace paths are correctly routed."""
import pytest
from sgit_ai.cli.CLI__Main    import CLI__Main
from sgit_ai.cli.CLI__Stash   import CLI__Stash
from sgit_ai.cli.CLI__Share   import CLI__Share
from sgit_ai.cli.CLI__Publish import CLI__Publish
from sgit_ai.cli.CLI__Export  import CLI__Export


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

    def test_vault_export_routes_to_cmd_export(self):
        _, p = _build()
        args = p.parse_args(['vault', 'export'])
        assert args.func.__self__.__class__ is CLI__Export
        assert args.func.__func__ is CLI__Export.cmd_export

    def test_share_send_routes_to_cmd_send(self):
        _, p = _build()
        args = p.parse_args(['share', 'send', '--text', 'hello'])
        assert args.func.__self__.__class__ is CLI__Share
        assert args.func.__func__ is CLI__Share.cmd_send

    def test_share_receive_routes_to_cmd_receive(self):
        _, p = _build()
        args = p.parse_args(['share', 'receive', 'word-word-1234'])
        assert args.func.__self__.__class__ is CLI__Share
        assert args.func.__func__ is CLI__Share.cmd_receive

    def test_share_publish_routes_to_cmd_publish(self):
        _, p = _build()
        args = p.parse_args(['share', 'publish'])
        assert args.func.__self__.__class__ is CLI__Publish
        assert args.func.__func__ is CLI__Publish.cmd_publish

    def test_share_namespace_has_send_receive_publish(self):
        _, p = _build()
        share_sub = p._subparsers._group_actions[0].choices['share']
        share_choices = share_sub._subparsers._group_actions[0].choices
        assert 'send'    in share_choices
        assert 'receive' in share_choices
        assert 'publish' in share_choices

    def test_vault_namespace_has_stash_remote_export(self):
        _, p = _build()
        vault_sub = p._subparsers._group_actions[0].choices['vault']
        vault_choices = vault_sub._subparsers._group_actions[0].choices
        assert 'stash'  in vault_choices
        assert 'remote' in vault_choices
        assert 'export' in vault_choices


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

    def test_old_publish_not_a_top_level_command(self):
        assert 'publish' not in self._top_level_choices()

    def test_old_export_not_a_top_level_command(self):
        assert 'export' not in self._top_level_choices()

    def test_old_remote_not_a_top_level_command(self):
        assert 'remote' not in self._top_level_choices()


# ---------------------------------------------------------------------------
# Top-level count guard
# ---------------------------------------------------------------------------

class Test_B07__Top_Level_Count:

    def test_real_top_level_commands_within_limit(self):
        cli = CLI__Main()
        p   = cli.build_parser()
        all_choices = set(p._subparsers._group_actions[0].choices.keys())
        assert len(all_choices) <= 26, f'Too many top-level commands: {sorted(all_choices)}'
