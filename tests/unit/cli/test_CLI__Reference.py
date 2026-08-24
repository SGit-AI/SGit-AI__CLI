"""CLI__Reference — the generated command surface.

The point of this class is that it cannot drift from the code, so the tests
assert the *generation* property (every command the parser has, none it does
not) rather than a frozen list of command names.
"""
import json

from sgit_ai.cli.CLI__Reference import CLI__Reference, REFERENCE_SCHEMA


class Test_CLI__Reference:

    def setup_method(self):
        self.reference = CLI__Reference()

    def test_walk_finds_every_parser_command_and_no_others(self):
        """The generated set is exactly the parser's set — the anti-drift property."""
        import argparse

        parser   = self.reference.build_parser()
        expected = set()

        def collect(node, prefix=''):
            for action in node._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, child in action.choices.items():
                        path = f'{prefix} {name}'.strip()
                        expected.add(path)
                        collect(child, path)

        collect(parser)
        generated = {command['path'] for command in self.reference.walk()}
        assert generated == expected

    def test_the_static_publishing_commands_are_present(self):
        """A regression guard for the specific gap this was built to close:
        the README described none of these when the generator was written."""
        paths = {command['path'] for command in self.reference.walk()}
        for path in ('publish', 'vault serve', 'vault mirror',
                     'vault attach', 'vault ignore', 'vault move'):
            assert path in paths, f'{path} missing from the generated reference'

    def test_flags_come_from_the_parser_with_their_help(self):
        publish = next(c for c in self.reference.walk() if c['path'] == 'publish')
        flags   = {flag for option in publish['options'] for flag in option['flags']}
        assert '--visibility' in flags
        assert '--bundles'    in flags
        visibility = next(o for o in publish['options'] if '--visibility' in o['flags'])
        assert visibility['choices'] == ['bare', 'named', 'public']   # read off the parser
        assert '-h' not in flags and '--help' not in flags            # noise excluded

    def test_json_is_stable_and_diffable(self):
        """Two renders must be byte-identical, or release diffs are noise."""
        first  = self.reference.render('json')
        second = CLI__Reference().render('json')
        assert first == second
        data = json.loads(first)
        assert data['schema']        == REFERENCE_SCHEMA
        assert data['command_count'] == len(data['commands'])
        assert data['command_count'] > 50
        paths = [command['path'] for command in data['commands']]
        assert paths == sorted(paths, key=lambda p: p) or len(paths) == len(set(paths))

    def test_version_is_the_real_release_version(self):
        """Regression: `_version.py` was a stale literal (v0.1.0) while the
        released package was v0.16.1, and publish stamps it into every
        manifest as `generated_by`."""
        from sgit_ai._version import VERSION
        assert VERSION != 'v0.1.0'
        assert self.reference.as_json()['cli_version'] == str(VERSION)

    def test_markdown_and_llms_render_every_command(self):
        commands = self.reference.walk()
        markdown = self.reference.render('markdown')
        llms     = self.reference.render('llms')
        for command in commands:
            assert f'sgit {command["path"]}' in markdown
            assert f'sgit {command["path"]}:' in llms
        assert markdown.startswith('# sgit command reference')
        assert 'llms' not in markdown.split('\n')[0]

    def test_version_is_not_double_prefixed(self):
        """VERSION already carries its leading 'v' — the headers must not add another."""
        from sgit_ai._version import VERSION
        assert str(VERSION).startswith('v')
        assert 'vv' not in self.reference.render('llms')
        assert 'vv' not in self.reference.render('markdown')

    def test_unknown_format_falls_back_to_json(self):
        assert json.loads(self.reference.render('not-a-format'))['schema'] == REFERENCE_SCHEMA


class Test_CLI__Reference__Wired_Into_Help:
    """It is reached through `sgit help --format`, not a new top-level command:
    the B07 count guard makes new top-level commands argue for their place, and
    `help all` is already "show the full command surface"."""

    def test_help_accepts_the_machine_formats(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        parser = CLI__Main().build_parser()
        for output_format in ('text', 'json', 'markdown', 'llms'):
            assert parser.parse_args(['help', '--format', output_format]).format == output_format

    def test_help_defaults_to_text(self):
        from sgit_ai.cli.CLI__Main import CLI__Main
        assert CLI__Main().build_parser().parse_args(['help']).format == 'text'

    def test_no_new_top_level_command_was_added(self):
        """Regression: this was first built as top-level `sgit reference`, which
        broke the B07 top-level count guard."""
        import argparse
        from sgit_ai.cli.CLI__Main import CLI__Main
        parser = CLI__Main().build_parser()
        top    = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)][0]
        assert 'reference' not in top.choices
        assert len(top.choices) <= 32

    def test_json_format_emits_the_contract(self, capsys):
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['help', '--format', 'json'])
        args.func(args)
        assert json.loads(capsys.readouterr().out)['schema'] == REFERENCE_SCHEMA

    def test_output_file_is_written(self, tmp_path, capsys):
        from sgit_ai.cli.CLI__Main import CLI__Main
        target = tmp_path / 'ref.json'
        cli    = CLI__Main()
        parser = cli.build_parser()
        args   = parser.parse_args(['help', '--format', 'json', '-o', str(target)])
        args.func(args)
        assert json.loads(target.read_text())['command_count'] > 50
        assert 'Wrote' in capsys.readouterr().out
