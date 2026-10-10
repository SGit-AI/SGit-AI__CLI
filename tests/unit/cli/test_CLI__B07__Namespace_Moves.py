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
# Top-level command list (placement rule, CLAUDE.md rule 9)
# ---------------------------------------------------------------------------

# Every command goes where it belongs: a daily-use verb at the top level, anything
# about the vault as a whole under `vault`, anything about commits under `history`,
# and so on. The top level is not capped by a number. It is this explicit list, so
# adding or removing a top-level command is a deliberate, reviewed edit here, never
# an accident and never a reason to put a command somewhere it does not belong.
TOP_LEVEL_COMMANDS = {
    'branch', 'cache', 'cat', 'check', 'clone', 'clone-branch', 'clone-headless', 'clone-range',
    'commit', 'create', 'dev', 'doctor', 'fetch', 'file', 'help', 'history', 'init', 'inspect',
    'ls', 'merge-abort', 'migrate', 'pki', 'publish', 'pull', 'push', 'remote', 'resolve',
    'status', 'update', 'vault', 'version', 'write',
}


class Test_B07__Top_Level_Commands:

    def test_top_level_commands_are_exactly_the_reviewed_list(self):
        cli = CLI__Main()
        p   = cli.build_parser()
        all_choices = set(p._subparsers._group_actions[0].choices.keys())
        added   = sorted(all_choices - TOP_LEVEL_COMMANDS)
        removed = sorted(TOP_LEVEL_COMMANDS - all_choices)
        assert not added and not removed, (
            f'top-level commands changed (added {added}, removed {removed}). If that is where they '
            f'belong, update TOP_LEVEL_COMMANDS in this file (see CLAUDE.md rule 9).')
