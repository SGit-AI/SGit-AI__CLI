"""Stub used to disable a CLI command without removing its argparse wiring.

A command surface that relies on the current insecure Simple Token scheme
(`vault export`, `vault share`, `share send`, `share publish`) is wired to
this stub via `set_defaults(func=disabled.cmd_disabled)` instead of its real
handler. The backend implementations of those commands remain importable and
unit-tested — only the user-facing entry point is shut.
"""
import sys

from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.safe_types.Safe_Str__CLI_Command_Label           import Safe_Str__CLI_Command_Label


class CLI__Disabled_Command(Type_Safe):
    command_name : Safe_Str__CLI_Command_Label = None    # e.g. 'sgit vault share'

    def cmd_disabled(self, args):
        name      = str(self.command_name) if self.command_name else '(unknown)'
        full_argv = ' '.join(['sgit'] + sys.argv[1:]) if len(sys.argv) > 1 else f'sgit {name.removeprefix("sgit ").strip()}'
        print(f'error: `{name}` is temporarily disabled pending a security '
              f'rework of the Simple Token scheme.', file=sys.stderr)
        print(f'  You ran: {full_argv}', file=sys.stderr)
        print('  Your flags were parsed but ignored — the disablement is on '
              'the whole command, not any specific flag.', file=sys.stderr)
        print('  The backend implementation is preserved and will be re-exposed '
              'once the new token scheme lands.', file=sys.stderr)
        print('  See CHANGELOG.md and the project release notes for status '
              'and timeline.', file=sys.stderr)
        sys.exit(2)
