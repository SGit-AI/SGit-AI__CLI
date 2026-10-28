"""CLI__Argv__Signing — Git's signing flags on the commands that make commits and tags
(design__02 §3.1, 3.3).

Git's key form is attached: `-S<key>` / `--gpg-sign=<key>`. A bare `-S` is a flag, so
`sgit commit -S "msg"` keeps "msg" as the message. normalise() rewrites the attached
forms to a hidden `--gpg-sign-key <key>` plus the flag, only inside a signing command
and only before `--` (after it everything is a path)."""
import argparse
from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   sgit_ai.safe_types.Enum__Sign_Choice             import Enum__Sign_Choice
from   sgit_ai.schemas.Schema__Signing_Flags            import Schema__Signing_Flags

SIGNING_COMMANDS = (('commit',), ('write',), ('pull',), ('branch', 'merge'), ('history', 'revert'))


class CLI__Argv__Signing(Type_Safe):

    def normalise(self, argv: list) -> list:
        start = self.command_end(argv)
        if start < 0:
            return list(argv)
        out = list(argv[:start])
        for i, word in enumerate(argv[start:], start=start):
            if word == '--':
                return out + list(argv[i:])
            if word.startswith('-S') and len(word) > 2 and not word.startswith('--'):
                out += ['--gpg-sign-key', word[2:], '-S']
            elif word.startswith('--gpg-sign='):
                out += ['--gpg-sign-key', word[len('--gpg-sign='):], '--gpg-sign']
            else:
                out.append(word)
        return out

    def command_end(self, argv: list) -> int:
        """The index just after a signing command's words, or -1 when argv is no such command."""
        for i, word in enumerate(argv):
            for words in SIGNING_COMMANDS:
                if tuple(argv[i:i + len(words)]) == words:
                    return i + len(words)
            if not word.startswith('-') and word not in ('commit', 'write', 'pull', 'branch', 'history'):
                if i == 0 or not argv[i - 1].startswith('--'):                  # a global option's value is skipped
                    return -1
        return -1

    def add_flags(self, parser) -> None:
        parser.add_argument('-S', '--gpg-sign', dest='gpg_sign', action='store_true', default=False,
                            help='Also sign with your own key (user.signingKey: SSH or OpenPGP), as git -S. '
                                 '-S<KEY> / --gpg-sign=<KEY> name the key')
        parser.add_argument('--gpg-sign-key', dest='gpg_sign_key', default=None, help=argparse.SUPPRESS)
        parser.add_argument('--no-gpg-sign', dest='no_gpg_sign', action='store_true', default=False,
                            help='Do not sign with your own key, even when sgit.gpgSign is set')

    def add_tag_flags(self, parser) -> None:
        parser.add_argument('-s', '--sign', dest='gpg_sign', action='store_true', default=False,
                            help='Also sign the tag with your own key (user.signingKey), as git tag -s')
        parser.add_argument('-u', '--local-user', dest='gpg_sign_key', default=None, metavar='KEY',
                            help='Sign the tag with this key (implies -s), as git tag -u')
        parser.add_argument('--no-sign', dest='no_gpg_sign', action='store_true', default=False,
                            help='Do not sign with your own key, even when sgit.gpgSign is set')

    def flags_from(self, args) -> Schema__Signing_Flags:
        """None when the command line said nothing (the Git config decides)."""
        key = getattr(args, 'gpg_sign_key', None)
        if getattr(args, 'no_gpg_sign', False) is True:
            return Schema__Signing_Flags(sign=Enum__Sign_Choice.OFF)
        if key or getattr(args, 'gpg_sign', False) is True:
            return Schema__Signing_Flags(sign=Enum__Sign_Choice.ON, key=key or None)
        return None
