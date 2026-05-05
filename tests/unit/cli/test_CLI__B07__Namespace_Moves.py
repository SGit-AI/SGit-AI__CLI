"""Tests for B07 CLI cruft moves — new namespace paths + wrong-context friendly errors.

Verifies:
  - stash / remote / export live under `vault`
  - send / receive / publish live under `share`
  - Old top-level invocations print a friendly 'has moved' error and exit(1)
"""
import sys
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
# Wrong-context friendly errors — old top-level commands print hint + exit(1)
# ---------------------------------------------------------------------------

class Test_B07__Wrong_Context_Friendly_Errors:

    def _run_old(self, args_list, capsys):
        cli = CLI__Main()
        with pytest.raises(SystemExit) as exc:
            cli.run(args_list)
        assert exc.value.code == 1
        return capsys.readouterr().err

    def test_old_stash_prints_hint(self, capsys):
        err = self._run_old(['stash'], capsys)
        assert 'vault stash' in err
        assert 'has moved' in err

    def test_old_remote_prints_hint(self, capsys):
        err = self._run_old(['remote'], capsys)
        assert 'vault remote' in err

    def test_old_export_prints_hint(self, capsys):
        err = self._run_old(['export'], capsys)
        assert 'vault export' in err

    def test_old_send_prints_hint(self, capsys):
        err = self._run_old(['send'], capsys)
        assert 'share send' in err

    def test_old_receive_prints_hint(self, capsys):
        err = self._run_old(['receive'], capsys)
        assert 'share receive' in err

    def test_old_publish_prints_hint(self, capsys):
        err = self._run_old(['publish'], capsys)
        assert 'share publish' in err


# ---------------------------------------------------------------------------
# Top-level count guard
# ---------------------------------------------------------------------------

class Test_B07__Top_Level_Count:

    def test_real_top_level_commands_within_limit(self):
        from sgit_ai.cli.CLI__Main import _RENAME_MAP
        cli = CLI__Main()
        p   = cli.build_parser()
        all_choices  = set(p._subparsers._group_actions[0].choices.keys())
        rename_names = set(_RENAME_MAP.keys())
        real         = all_choices - rename_names
        assert len(real) <= 26, f'Too many real top-level commands: {sorted(real)}'
