"""CLI__Blame — `sgit history blame [<rev>] [-L <range>]… [-w] [--first-parent] [-s] [-e]
[--abbrev N] [--porcelain | --line-porcelain | --json] [--text] [--offline] [--] <path>`
(design__04 §3.2): Git's three output shapes, so tools that read `git blame` read ours."""
import datetime
import json
import sys
from   osbot_utils.type_safe.Type_Safe                     import Type_Safe
from   sgit_ai.core.Vault__Path_Quote                      import Vault__Path_Quote
from   sgit_ai.core.actions.history.Vault__Blame           import Vault__Blame
from   sgit_ai.crypto.Vault__Crypto                        import Vault__Crypto

ID_PREFIX = 'obj-cas-imm-'


class CLI__Blame(Type_Safe):

    def register_args(self, parser) -> None:
        parser.add_argument('target', nargs='+', metavar='[REV] PATH', help='The file, optionally after a revision')
        parser.add_argument('-L', dest='ranges', action='append', default=None, metavar='RANGE',
                            help='Only these lines: N,M  N,+K  N,-K  /regex/  /regex/,+K (repeatable)')
        parser.add_argument('-w', dest='ignore_whitespace', action='store_true', help='Ignore whitespace changes')
        parser.add_argument('--first-parent', action='store_true', help='Follow only the first parent of merges')
        parser.add_argument('-s', dest='suppress', action='store_true', help='No author and date columns')
        parser.add_argument('-e', dest='show_key', action='store_true', help='The signing key id instead of the branch name')
        parser.add_argument('--abbrev', type=int, default=12, help='Commit id characters (default 12)')
        parser.add_argument('--porcelain', action='store_true', help="Git's machine format")
        parser.add_argument('--line-porcelain', dest='line_porcelain', action='store_true',
                            help='The machine format with commit details on every line')
        parser.add_argument('--json', dest='json_out', action='store_true', help='One JSON object (history_blame_v1)')
        parser.add_argument('--text', action='store_true', help='Blame a binary file line by line')
        parser.add_argument('--offline', action='store_true', help='Never fetch a blob this clone does not hold')
        parser.add_argument('-d', '--directory', default='.', help='Vault directory (default: .)')
        parser.set_defaults(func=self.cmd_blame)

    def cmd_blame(self, args):
        if len(args.target) > 2:
            print('error: sgit history blame takes [REV] PATH', file=sys.stderr)
            sys.exit(2)
        rev, path = (args.target[0], args.target[1]) if len(args.target) == 2 else ('', args.target[0])
        engine = Vault__Blame(crypto=Vault__Crypto(), ignore_whitespace=args.ignore_whitespace is True,
                              first_parent=args.first_parent is True, text=args.text is True,
                              offline=args.offline is True, api=self.remote_api(args))
        result = engine.blame(args.directory, path.lstrip('./') if path.startswith('./') else path, rev=rev,
                              ranges=args.ranges)
        if args.json_out:
            print(json.dumps(result.json()))
        elif args.porcelain or args.line_porcelain:
            print(self.porcelain(result, repeat=args.line_porcelain is True), end='')
        else:
            print(self.default_format(result, args), end='')
        self.notes(result)

    def remote_api(self, args):
        """The clone's own server when it has a remote, for blobs a sparse clone lacks (D9)."""
        try:
            from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
            store    = CLI__Token_Store()
            base_url = store.resolve_base_url(None, args.directory)
            token    = store.resolve_token(None, args.directory)
            if not base_url or not token:
                return None
            from sgit_ai.network.api.Vault__API import Vault__API
            return Vault__API(base_url=base_url, access_token=token)
        except Exception:
            return None

    # --- formats ------------------------------------------------------------------------

    def short(self, commit_id: str, abbrev: int, boundary: bool) -> str:
        hex_part = commit_id[len(ID_PREFIX):] if commit_id.startswith(ID_PREFIX) else commit_id
        return ('^' + hex_part[:max(abbrev - 1, 1)]) if boundary else hex_part[:abbrev]

    def when(self, timestamp_ms: int) -> str:
        return datetime.datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=datetime.timezone.utc) \
                       .strftime('%Y-%m-%d %H:%M:%S +0000')

    def author(self, info, show_key: bool) -> str:
        return str(info.author_key_id or 'unsigned') if show_key else str(info.author or 'unknown')

    def default_format(self, result, args) -> str:
        quote     = Vault__Path_Quote()
        paths     = {str(l.orig_path) for l in result.lines}
        show_path = paths != {str(result.path)}
        width     = len(str(len(result.lines) and max(int(l.final_line) for l in result.lines)))
        path_w    = max((len(quote.quote(p)) for p in paths), default=0)
        author_w  = max((len(self.author(result.commits[str(l.commit_id)], args.show_key)) for l in result.lines), default=0)
        out = []
        for line in result.lines:
            info = result.commits[str(line.commit_id)]
            row  = self.short(str(line.commit_id), args.abbrev, info.boundary)
            if show_path:
                row += f' {quote.quote(str(line.orig_path)):<{path_w}}'
            if args.suppress:
                row += f' {int(line.final_line):>{width}}) '
            else:
                row += f' ({self.author(info, args.show_key):<{author_w}} {self.when(info.timestamp_ms)} ' \
                       f'{int(line.final_line):>{width}}) '
            out.append(row + str(line.text) + '\n')
        return ''.join(out)

    def porcelain(self, result, repeat: bool) -> str:
        out, seen, previous = [], set(), None
        for line in result.lines:
            cid, info = str(line.commit_id), result.commits[str(line.commit_id)]
            group     = (cid, str(line.orig_path), int(line.orig_line) - 1)
            new_group = previous is None or group != (previous[0], previous[1], previous[2])
            if new_group or repeat:
                size = self.group_size(result.lines, line) if new_group else None
                out.append(f'{cid} {int(line.orig_line)} {int(line.final_line)}' + (f' {size}' if size else '') + '\n')
                if repeat or cid not in seen:
                    out += self.details(info, cid, str(line.orig_path))
                    seen.add(cid)
            else:
                out.append(f'{cid} {int(line.orig_line)} {int(line.final_line)}\n')
            out.append('\t' + str(line.text) + '\n')
            previous = (cid, str(line.orig_path), int(line.orig_line))
        return ''.join(out)

    def group_size(self, lines: list, first) -> int:
        start, size = lines.index(first), 0
        for k in range(start, len(lines)):
            here = lines[k]
            if (str(here.commit_id), str(here.orig_path)) != (str(first.commit_id), str(first.orig_path)) or \
                    int(here.orig_line) != int(first.orig_line) + size or int(here.final_line) != int(first.final_line) + size:
                break
            size += 1
        return size

    def details(self, info, commit_id: str, path: str) -> list:
        author  = str(info.author or 'unknown')
        mail    = f'<{info.author_key_id or "unsigned"}>'
        seconds = int(info.timestamp_ms) // 1000
        rows    = [f'author {author}\n', f'author-mail {mail}\n', f'author-time {seconds}\n', 'author-tz +0000\n',
                   f'committer {author}\n', f'committer-mail {mail}\n', f'committer-time {seconds}\n',
                   'committer-tz +0000\n', f'summary {info.summary or ""}\n']
        if info.boundary:
            rows.append('boundary\n')
        if info.previous_id:
            rows.append(f'previous {info.previous_id} {info.previous_path}\n')
        rows.append(f'filename {path}\n')
        return rows

    def notes(self, result) -> None:
        if str(result.boundary_reason or '') == 'shallow':
            print('… blame stops at the shallow boundary (lines marked ^ may be older). '
                  'Deepen with: sgit fetch --unshallow', file=sys.stderr)
        elif str(result.boundary_reason or '') == 'offline':
            print('… some history is not in this clone and could not be fetched: lines marked ^ stop there',
                  file=sys.stderr)
