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

    def test_stub_prints_message_and_exits(self, capsys):
        cli  = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            cli._cmd_clone_branch_stub(type('A', (), {'bare': False})())
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert 'B09' in err
        assert 'clone-branch' in err

    def test_stub_message_mentions_full_clone_alternative(self, capsys):
        cli = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit):
            cli._cmd_clone_branch_stub(type('A', (), {'bare': False})())
        err = capsys.readouterr().err
        assert 'sgit clone' in err


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

    def test_stub_prints_message_and_exits(self, capsys):
        cli = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            cli._cmd_clone_headless_stub(type('A', (), {'bare': False})())
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert 'clone-headless' in err
        assert 'B09' in err

    def test_bare_flag_rejected_with_friendly_error(self, capsys):
        """clone-headless --bare is redundant — headless is already bare-equivalent."""
        cli = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            cli._cmd_clone_headless_stub(type('A', (), {'bare': True})())
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert 'redundant' in err or 'bare-equivalent' in err


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

    def test_stub_prints_message_and_exits(self, capsys):
        cli = CLI__Main()
        cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            cli._cmd_clone_range_stub(type('A', (), {'bare': False})())
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert 'clone-range' in err
        assert 'B09' in err
