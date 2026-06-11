"""Tests for CLI__Disabled_Command.

The four Simple-Token-creating commands (`sgit vault export`, `sgit vault share`,
`sgit share send`, `sgit share publish`) are routed to this stub. Backend
implementations are kept and tested separately under tests/unit/transfer/
and tests/qa/.
"""
import argparse
import sys

import pytest

from sgit_ai.cli.CLI__Disabled_Command import CLI__Disabled_Command
from sgit_ai.cli.CLI__Main             import CLI__Main


class Test_CLI__Disabled_Command:

    def test_cmd_disabled_exits_nonzero_with_clear_message(self, capsys):
        stub = CLI__Disabled_Command(command_name='sgit vault share')
        with pytest.raises(SystemExit) as exc:
            stub.cmd_disabled(args=None)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert 'sgit vault share' in err
        assert 'disabled'         in err
        assert 'Simple Token'     in err
        assert 'backend'          in err.lower()

    def test_cmd_disabled_handles_missing_command_name(self, capsys):
        stub = CLI__Disabled_Command()
        with pytest.raises(SystemExit) as exc:
            stub.cmd_disabled(args=None)
        assert exc.value.code == 1
        assert '(unknown)' in capsys.readouterr().err


class Test_CLI__Main__Disabled_Routes:
    """Argparse-level wiring: confirm each of the four commands routes to the stub
    and that `share receive` (kept) routes to its real handler."""

    @classmethod
    def setup_class(cls):
        cls.parser = CLI__Main().build_parser()

    def _exits_with_disabled_message(self, argv, expected_label, capsys):
        args = self.parser.parse_args(argv)
        with pytest.raises(SystemExit) as exc:
            args.func(args)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert expected_label in err
        assert 'disabled'     in err

    def test_vault_export_is_disabled(self, capsys):
        self._exits_with_disabled_message(['vault', 'export', '.'], 'sgit vault export', capsys)

    def test_vault_share_is_disabled(self, capsys):
        self._exits_with_disabled_message(['vault', 'share', '.'], 'sgit vault share', capsys)

    def test_share_send_is_disabled(self, capsys):
        self._exits_with_disabled_message(['share', 'send', '--text', 'hi'], 'sgit share send', capsys)

    def test_share_publish_is_disabled(self, capsys):
        self._exits_with_disabled_message(['share', 'publish', '.'], 'sgit share publish', capsys)

    def test_share_receive_is_NOT_disabled(self):
        """`share receive` consumes tokens; it must NOT be routed to the disabled stub."""
        args = self.parser.parse_args(['share', 'receive', 'coral-equal-1234'])
        bound_instance = getattr(args.func, '__self__', None)
        if bound_instance is not None:
            assert bound_instance.__class__.__name__ != 'CLI__Disabled_Command'

    def test_help_marks_disabled_commands(self):
        """The four disabled commands carry the [disabled] tag in their help."""
        sub_action   = next(a for a in self.parser._actions if a.dest == 'command')
        vault_parser = sub_action.choices['vault']
        share_parser = sub_action.choices['share']
        assert '[disabled]' in vault_parser.format_help()    # vault export + vault share
        assert '[disabled]' in share_parser.format_help()    # share send + share publish
