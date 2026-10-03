"""CLI__Reference — the command surface, generated from the live argparse tree.

Hand-written command documentation drifts: a flag is added, renamed or removed
in `register()` and the README, the skill file and sgit.ai keep describing the
old surface. This walks the parser `CLI__Main.build_parser()` actually returns,
so the output *is* the code — it cannot describe a command that does not exist,
and it cannot miss one that does.

Consumed by `sgit help --format`, whose JSON form is the hand-off contract for
the sgit.ai / llms.txt agent: diff two releases' JSON to get exactly what
changed, rather than re-reading the CHANGELOG and guessing.
"""
import argparse

from osbot_utils.type_safe.Type_Safe import Type_Safe

from sgit_ai._version import VERSION

REFERENCE_SCHEMA = 'sgit-cli-reference-v1'


class CLI__Reference(Type_Safe):

    def build_parser(self) -> argparse.ArgumentParser:
        from sgit_ai.cli.CLI__Main import CLI__Main
        return CLI__Main().build_parser()

    def sub_action(self, parser) -> argparse._SubParsersAction:
        """The sub-parsers action of a parser, or None when it is a leaf."""
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return action
        return None

    def option_entries(self, parser) -> list:
        """Flags declared directly on this parser, excluding -h/--help."""
        entries = []
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                continue
            if not action.option_strings:
                continue
            if action.option_strings == ['-h', '--help'] or '--help' in action.option_strings:
                continue
            entries.append(dict(flags   = list(action.option_strings),
                                help    = (action.help or '').strip(),
                                choices = sorted(str(c) for c in action.choices) if action.choices else []))
        return sorted(entries, key=lambda entry: entry['flags'][0])

    def positional_entries(self, parser) -> list:
        """Positional arguments declared directly on this parser."""
        entries = []
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                continue
            if action.option_strings:
                continue
            entries.append(dict(name     = action.dest,
                                help     = (action.help or '').strip(),
                                required = action.nargs not in ('?', '*')))
        return entries

    def walk(self, parser=None, prefix: str = '', seen: set = None) -> list:
        """Every command in the tree, depth-first, sorted — {path, help, options, positionals}.

        Sorted so two releases' output diffs cleanly; `seen` guards against the
        same parser object being reachable twice (aliases).
        """
        if parser is None:
            parser = self.build_parser()
        if seen is None:
            seen = set()
        commands   = []
        sub_action = self.sub_action(parser)
        if sub_action is None:
            return commands
        help_by_name = {}
        for choice_action in sub_action._choices_actions:
            help_by_name[choice_action.dest] = (choice_action.help or '').strip()
        for name in sorted(sub_action.choices):
            child = sub_action.choices[name]
            if id(child) in seen:
                continue
            seen.add(id(child))
            path = f'{prefix} {name}'.strip()
            commands.append(dict(path        = path,
                                 help        = help_by_name.get(name, ''),
                                 options     = self.option_entries(child),
                                 positionals = self.positional_entries(child)))
            commands.extend(self.walk(child, path, seen))
        return commands

    def as_json(self) -> dict:
        """The machine-readable contract: schema, version, every command."""
        commands = self.walk()
        return dict(schema        = REFERENCE_SCHEMA,
                    cli_version   = str(VERSION),
                    command_count = len(commands),
                    commands      = commands)

    def as_markdown(self) -> str:
        """A drop-in command reference — one section per top-level command."""
        lines = [f'# sgit command reference ({VERSION})',
                 '',
                 'Generated from the CLI parser by `sgit help --format markdown`.',
                 'Do not hand-edit: regenerate it.',
                 '']
        for command in self.walk():
            depth  = command['path'].count(' ')
            lines.append(f'{"#" * min(depth + 2, 6)} `sgit {command["path"]}`')
            lines.append('')
            if command['help']:
                lines.append(command['help'])
                lines.append('')
            for positional in command['positionals']:
                suffix = '' if positional['required'] else ' *(optional)*'
                lines.append(f'- `{positional["name"]}`{suffix} — {positional["help"]}')
            for option in command['options']:
                flags   = ', '.join(f'`{flag}`' for flag in option['flags'])
                choices = f' ({" | ".join(option["choices"])})' if option['choices'] else ''
                lines.append(f'- {flags}{choices} — {option["help"]}')
            if command['positionals'] or command['options']:
                lines.append('')
        return '\n'.join(lines).rstrip() + '\n'

    def as_llms_txt(self) -> str:
        """An llms.txt-style flat index: one line per command, agent-readable."""
        lines = [f'# sgit CLI {VERSION} — command index',      # VERSION already carries the 'v'
                 '',
                 '> Generated from the CLI parser. Every line is a real command in this',
                 '> release. Flags shown are those the parser accepts.',
                 '']
        for command in self.walk():
            flags = ' '.join(option['flags'][-1] for option in command['options'])
            lines.append(f'- sgit {command["path"]}: {command["help"] or "(no help text)"}'
                         + (f' [{flags}]' if flags else ''))
        return '\n'.join(lines) + '\n'

    def render(self, output_format: str = 'json') -> str:
        import json
        if output_format == 'markdown':
            return self.as_markdown()
        if output_format == 'llms':
            return self.as_llms_txt()
        return json.dumps(self.as_json(), indent=2) + '\n'
