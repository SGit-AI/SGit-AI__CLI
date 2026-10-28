"""CLI__Grep — `sgit grep` and `sgit file grep` (design__04 §3.3): git grep's options, its
output shapes (`path:text`, `rev:path:line:text`, `-` for context, `--` between groups,
`path:count`, `Binary file … matches`) and its exit codes: 0 a match, 1 none, 2 an error."""
import json
import os
import sys
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.core.Vault__Path_Quote                     import Vault__Path_Quote
from   sgit_ai.core.actions.history.Vault__Grep           import Vault__Grep
from   sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto


class CLI__Grep(Type_Safe):

    def register_args(self, parser) -> None:
        """The parser is made with add_help=False: -h is git grep's "no file names"; --help stays."""
        parser.add_argument('--help', action='help', help='Show this help')
        parser.add_argument('positionals', nargs='*', metavar='PATTERN [REV…]',
                            help='The pattern (unless -e), then revisions to search instead of the working copy; '
                                 'paths go after --')
        parser.add_argument('-e', dest='patterns', action='append', default=None, metavar='PATTERN',
                            help='A pattern (repeatable: lines matching any)')
        for flags, dest, text in ((('-i', '--ignore-case'), 'ignore_case', 'Ignore case'),
                                  (('-w', '--word-regexp'), 'word', 'Match whole words'),
                                  (('-v', '--invert-match'), 'invert', 'Lines that do not match'),
                                  (('-F', '--fixed-strings'), 'fixed', 'The pattern is a literal string'),
                                  (('-E', '--extended-regexp'), 'extended', 'Accepted: patterns are Python regexes'),
                                  (('-P', '--perl-regexp'), 'perl', 'Accepted: patterns are Python regexes'),
                                  (('-n', '--line-number'), 'line_number', 'Prefix line numbers'),
                                  (('-c', '--count'), 'count', 'Print path:count'),
                                  (('-l', '--files-with-matches'), 'files_with', 'Print only the files that match'),
                                  (('-L', '--files-without-match'), 'files_without', 'Print only the files that do not'),
                                  (('-o', '--only-matching'), 'only_matching', 'Print only the matched parts'),
                                  (('-q', '--quiet'), 'quiet', 'Print nothing; the exit code tells'),
                                  (('-h',), 'no_filename', 'Do not print file names'),
                                  (('-H',), 'with_filename', 'Print file names (the default)'),
                                  (('-I',), 'skip_binary', 'Do not search binary files'),
                                  (('--text', '-a'), 'text', 'Search binary files as text'),
                                  (('--untracked',), 'untracked', 'Also search untracked files'),
                                  (('--json',), 'json_out', 'One JSON object (grep_v1)'),
                                  (('--offline',), 'offline', 'Never fetch a blob this clone does not hold')):
            parser.add_argument(*flags, dest=dest, action='store_true', default=False, help=text)
        parser.add_argument('-A', dest='after', type=int, default=0, metavar='N', help='N lines after each match')
        parser.add_argument('-B', dest='before', type=int, default=0, metavar='N', help='N lines before each match')
        parser.add_argument('-C', dest='context', type=int, default=None, metavar='N', help='N lines around each match')
        parser.add_argument('-m', '--max-count', dest='max_count', type=int, default=0, metavar='N',
                            help='Stop after N matching lines per file')
        parser.add_argument('-d', '--directory', default='.', help='Vault directory (default: .)')
        parser.set_defaults(func=self.cmd_grep)

    def cmd_grep(self, args):
        from sgit_ai.core.Vault__Errors import Vault__Revision_Error, Vault__Pathspec_Error
        try:
            found = self.run(args)
        except (Vault__Revision_Error, Vault__Pathspec_Error, ValueError, OSError) as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(2)
        sys.exit(0 if found else 1)

    def engine(self, args) -> Vault__Grep:
        from sgit_ai.core.Vault__Errors      import Vault__Revision_Error
        from sgit_ai.core.Vault__Regex_Guard import MAX_PATTERN_CHARS
        patterns   = list(args.patterns or [])
        positional = list(args.positionals or [])
        if not patterns:
            if not positional:
                raise ValueError('no pattern given')
            patterns.append(positional.pop(0))
        args.revs  = positional
        for pattern in patterns:                                       # before the safe type, so the guard's message
            if len(pattern) > MAX_PATTERN_CHARS:                       # and exit 2 apply, not a type error (BR-5)
                raise Vault__Revision_Error(f'grep pattern is {len(pattern)} characters; the limit is {MAX_PATTERN_CHARS}')
        before     = args.context if args.context is not None else args.before
        after      = args.context if args.context is not None else args.after
        grep = Vault__Grep(crypto=Vault__Crypto(), patterns=patterns, fixed=args.fixed, ignore_case=args.ignore_case,
                           word=args.word, invert=args.invert, untracked=args.untracked, text=args.text,
                           skip_binary=args.skip_binary, offline=args.offline, max_count=max(0, args.max_count),
                           before=max(0, before), after=max(0, after))
        grep.compile()
        return grep

    def pathspec(self, args):
        tail = list(getattr(args, 'pathspec_tail', None) or [])
        if not tail:
            return None
        for spec in tail:
            if spec.startswith(':'):
                raise ValueError(f"pathspec magic is not supported: '{spec}'")
        from sgit_ai.core.actions.commit.Vault__Pathspec import Vault__Pathspec
        return Vault__Pathspec().from_args(tail, os.getcwd(), args.directory)

    def run(self, args) -> bool:
        grep     = self.engine(args)
        pathspec = self.pathspec(args)
        sources  = [(rev, grep.revision_files(args.directory, rev, pathspec)) for rev in args.revs] or \
                   [('', grep.working_files(args.directory, pathspec))]
        quote, found, records = Vault__Path_Quote(), False, []
        context  = int(grep.before) or int(grep.after)
        printed_group = False
        for rev, files in sources:
            for path, data in files:
                result = grep.search(data)
                name   = (f'{rev}:' if rev else '') + quote.quote(path)
                if args.json_out:
                    records.append((rev, path, result))
                    found = found or result['matched']
                    continue
                if args.files_without:
                    if not result['matched']:
                        found = True
                        if not args.quiet:
                            print(name)
                    continue
                if not result['matched']:
                    continue
                found = True
                if args.quiet:
                    return True
                if args.files_with:
                    print(name)
                elif args.count:
                    print(f'{name}:{result["count"]}' if not args.no_filename else str(result['count']))
                elif result['binary']:
                    print(f'Binary file {name} matches')
                else:
                    printed_group = self.print_rows(args, name, result['rows'], context, printed_group)
        if args.json_out:
            print(json.dumps(self.as_json(args, grep, records)))
        return found

    def print_rows(self, args, name: str, rows: list, context: int, printed_group: bool) -> bool:
        previous = None
        for number, text, spans, is_match in rows:
            if context and (previous is None and printed_group or previous is not None and number != previous + 1):
                print('--')
            previous = number
            sep    = ':' if is_match else '-'
            prefix = '' if args.no_filename else f'{name}{sep}'
            if args.line_number:
                prefix += f'{number}{sep}'
            if args.only_matching:
                for start, end in spans:
                    print(prefix + self.printable(text[start:end]))
            else:
                print(prefix + self.printable(text))
        return printed_group or bool(rows)

    def printable(self, text: str) -> str:
        return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'replace')

    def as_json(self, args, grep, records: list) -> dict:
        matches = [dict(rev=rev, path=path, line=number, text=self.printable(text), spans=[list(s) for s in spans],
                        context=not is_match)
                   for rev, path, result in records for number, text, spans, is_match in result['rows']]
        return dict(schema='grep_v1', revs=list(args.revs), pattern=[str(p) for p in grep.patterns],
                    matches=matches, files_searched=len(records),
                    binary_matches=[path for _, path, result in records if result['binary'] and result['matched']],
                    skipped=dict(grep.skipped))
