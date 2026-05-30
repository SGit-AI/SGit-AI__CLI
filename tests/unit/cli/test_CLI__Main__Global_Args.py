"""Tests for global --token/--base-url placement relative to the subcommand.

Regression: the top-level parser and the shared `network_args` parent both
declare --token and --base-url. argparse applied the subparser's own defaults
over the already-populated namespace, so a value given *before* the subcommand
(`sgit --token X --base-url Y push`) was clobbered back to None — a frequent
first-try failure for agents that put flags before the command (git -C style).

Fix: the network_args copies use default=argparse.SUPPRESS, so when the flag is
absent at the subcommand level it is not written into the namespace and cannot
overwrite the global value; when present, the subcommand value still wins.
"""
import pytest
from sgit_ai.cli.CLI__Main import CLI__Main


class Test_CLI__Main__Global_Args:
    def setup_method(self):
        self.parser = CLI__Main().build_parser()

    # --- global flags BEFORE the subcommand (the reported bug) ---------------

    def test_global_token_before_subcommand(self):
        args = self.parser.parse_args(['--token', 'aws', 'push'])
        assert args.token == 'aws'

    def test_global_base_url_before_subcommand(self):
        args = self.parser.parse_args(['--base-url', 'https://dev.send.sgraph.ai', 'push'])
        assert args.base_url == 'https://dev.send.sgraph.ai'

    def test_global_token_and_base_url_before_subcommand(self):
        args = self.parser.parse_args(
            ['--base-url', 'https://dev.send.sgraph.ai', '--token', 'aws', 'push'])
        assert args.token    == 'aws'
        assert args.base_url == 'https://dev.send.sgraph.ai'

    # --- subcommand-level flags must still work (git-style after command) ----

    def test_subcommand_level_token_still_works(self):
        args = self.parser.parse_args(['push', '--token', 'aws'])
        assert args.token == 'aws'

    def test_subcommand_level_base_url_still_works(self):
        args = self.parser.parse_args(['push', '--base-url', 'https://dev.send.sgraph.ai'])
        assert args.base_url == 'https://dev.send.sgraph.ai'

    # --- precedence + defaults ----------------------------------------------

    def test_subcommand_token_overrides_global(self):
        args = self.parser.parse_args(['--token', 'GLOBAL', 'push', '--token', 'LOCAL'])
        assert args.token == 'LOCAL'

    def test_no_flags_default_to_none(self):
        args = self.parser.parse_args(['push'])
        assert args.token    is None
        assert args.base_url is None

    # --- applies to the other network commands too, not just push -----------

    @pytest.mark.parametrize('command', ['push', 'pull', 'fetch', 'status'])
    def test_global_token_before_each_network_command(self, command):
        args = self.parser.parse_args(['--token', 'aws', command])
        assert args.token == 'aws'
