"""Tests for B03 clone-family commands: clone --bare, clone-branch, clone-headless, clone-range."""
import sys

import pytest

from sgit_ai.cli.CLI__Main import CLI__Main


def _parser():
    return CLI__Main().build_parser()


# ---------------------------------------------------------------------------
# clone --bare parser
# ---------------------------------------------------------------------------

class Test_Clone_Bare_Parser:

    def test_bare_flag_parses(self):
        args = _parser().parse_args(['clone', 'pass:vault01', '--bare'])
        assert args.bare is True

    def test_bare_flag_defaults_false(self):
        args = _parser().parse_args(['clone', 'pass:vault01'])
        assert args.bare is False

    def test_bare_combines_with_sparse(self):
        args = _parser().parse_args(['clone', 'pass:vault01', '--sparse', '--bare'])
        assert args.bare is True
        assert args.sparse is True

    # Help text must surface the three accepted vault_key forms so users
    # don't trip into the "No branch index found" error that previously
    # came from passing a 64-hex read key as a passphrase.
    def test_clone_help_documents_all_three_vault_key_forms(self):
        import argparse
        parser = _parser()
        # Locate the 'clone' subparser to format its help directly
        subparsers_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        clone_parser     = subparsers_action.choices['clone']
        help_text        = clone_parser.format_help()
        assert '{passphrase}:{vault_id}'   in help_text
        assert '{read_key_hex}:{vault_id}' in help_text
        assert '--read-key'                in help_text
        assert '64-hex'                    in help_text                          # --read-key clarifies the format


# ---------------------------------------------------------------------------
# clone-branch  (stub)
# ---------------------------------------------------------------------------

class Test_Clone_Branch_Parser:

    def test_parser_exists(self):
        args = _parser().parse_args(['clone-branch', 'pass:vault01'])
        assert args.vault_key == 'pass:vault01'
        assert args.bare is False

    def test_parser_accepts_directory(self):
        args = _parser().parse_args(['clone-branch', 'pass:vault01', 'mydir'])
        assert args.directory == 'mydir'

    def test_bare_flag_parses(self):
        args = _parser().parse_args(['clone-branch', 'pass:vault01', 'mydir', '--bare'])
        assert args.bare is True

    def test_real_handler_exists(self):
        cli = CLI__Main()
        cli.build_parser()
        assert hasattr(cli, '_cmd_clone_branch')
        assert callable(cli._cmd_clone_branch)

    def test_parser_wired_to_real_handler(self):
        cli  = CLI__Main()
        parser = cli.build_parser()
        args = parser.parse_args(['clone-branch', 'pass:vault01'])
        assert args.func == cli._cmd_clone_branch


# ---------------------------------------------------------------------------
# clone-headless  (stub)
# ---------------------------------------------------------------------------

class Test_Clone_Headless_Parser:

    def test_parser_exists(self):
        args = _parser().parse_args(['clone-headless', 'pass:vault01'])
        assert args.vault_key == 'pass:vault01'

    def test_parser_accepts_optional_directory(self):
        args = _parser().parse_args(['clone-headless', 'pass:vault01', 'mydir'])
        assert args.directory == 'mydir'

    def test_real_handler_exists(self):
        cli = CLI__Main()
        cli.build_parser()
        assert hasattr(cli, '_cmd_clone_headless')
        assert callable(cli._cmd_clone_headless)

    def test_bare_flag_rejected_with_friendly_error(self, capsys):
        """clone-headless --bare is redundant — headless is already bare-equivalent."""
        cli = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            cli._cmd_clone_headless(type('A', (), {'bare': True})())
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert 'redundant' in err or 'bare-equivalent' in err

    def test_parser_wired_to_real_handler(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['clone-headless', 'pass:vault01'])
        assert args.func == cli._cmd_clone_headless


# ---------------------------------------------------------------------------
# clone-range  (stub)
# ---------------------------------------------------------------------------

class Test_Clone_Range_Parser:

    def test_parser_exists(self):
        args = _parser().parse_args(['clone-range', 'pass:vault01', 'abc..def'])
        assert args.vault_key == 'pass:vault01'
        assert args.range == 'abc..def'
        assert args.bare is False

    def test_parser_accepts_directory(self):
        args = _parser().parse_args(['clone-range', 'pass:vault01', 'abc..def', 'mydir'])
        assert args.directory == 'mydir'

    def test_bare_flag_parses(self):
        args = _parser().parse_args(['clone-range', 'pass:vault01', 'abc..def', '--bare'])
        assert args.bare is True

    def test_real_handler_exists(self):
        cli = CLI__Main()
        cli.build_parser()
        assert hasattr(cli, '_cmd_clone_range')
        assert callable(cli._cmd_clone_range)

    def test_parser_wired_to_real_handler(self):
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['clone-range', 'pass:vault01', 'abc..def'])
        assert args.func == cli._cmd_clone_range
