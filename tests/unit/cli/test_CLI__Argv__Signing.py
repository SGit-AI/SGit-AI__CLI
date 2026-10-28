import argparse

from sgit_ai.cli.CLI__Argv__Signing              import CLI__Argv__Signing
from sgit_ai.safe_types.Enum__Sign_Choice        import Enum__Sign_Choice


class Test_CLI__Argv__Signing:

    def setup_method(self):
        self.argv = CLI__Argv__Signing()

    def test_a_bare_dash_s_is_a_flag_so_the_message_stays_the_message(self):
        assert self.argv.normalise(['commit', '-S', 'msg']) == ['commit', '-S', 'msg']

    def test_the_attached_key_forms(self):
        assert self.argv.normalise(['commit', '-Skey', 'msg']) == ['commit', '--gpg-sign-key', 'key', '-S', 'msg']
        assert self.argv.normalise(['write', 'p', '--gpg-sign=k']) == ['write', 'p', '--gpg-sign-key', 'k', '--gpg-sign']
        assert self.argv.normalise(['branch', 'merge', '-Sk', 'x'])[:5] == ['branch', 'merge', '--gpg-sign-key', 'k', '-S']

    def test_after_double_dash_everything_is_a_path(self):
        assert self.argv.normalise(['commit', 'm', '--', '-Sfile']) == ['commit', 'm', '--', '-Sfile']

    def test_global_options_before_the_command_and_other_commands(self):
        assert self.argv.normalise(['--base-url', 'http://x', 'commit', '-Sk']) == \
               ['--base-url', 'http://x', 'commit', '--gpg-sign-key', 'k', '-S']
        assert self.argv.normalise(['status', '-Sk']) == ['status', '-Sk']
        assert self.argv.normalise(['history', 'log', '-Sk']) == ['history', 'log', '-Sk']

    def parse(self, *argv, tag=False):
        parser = argparse.ArgumentParser()
        (self.argv.add_tag_flags if tag else self.argv.add_flags)(parser)
        return self.argv.flags_from(parser.parse_args(self.argv.normalise(['commit'] + list(argv))[1:]))

    def test_flags(self):
        assert self.parse() is None                                             # the Git config decides
        assert self.parse('-S').sign == Enum__Sign_Choice.ON
        flags = self.parse('-Smy-key')
        assert (flags.sign, str(flags.key)) == (Enum__Sign_Choice.ON, 'my-key')
        assert self.parse('-S', '--no-gpg-sign').sign == Enum__Sign_Choice.OFF  # --no-gpg-sign wins
        assert str(self.parse('-u', 'k2', tag=True).key) == 'k2'
        assert self.parse('--no-sign', tag=True).sign == Enum__Sign_Choice.OFF
