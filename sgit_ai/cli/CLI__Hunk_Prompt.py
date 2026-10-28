"""CLI__Hunk_Prompt — `sgit commit -p`: choose hunks one by one, as `git add -p` does.

Keys (git 2.43's, less `e`, design__03 D4): y n a d s j k q ?. The prompt only
decides; the commit is made by `--hunk` semantics on the chosen ids, so the
interactive and the agent path commit through the same code. Ctrl-C (or end of
input) aborts with nothing chosen.
"""
import sys
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.schemas.commit.Schema__Hunk_List     import Schema__Hunk_List

HELP = '''y - commit this hunk
n - do not commit this hunk
q - quit; do not commit this hunk or any of the remaining ones
a - commit this hunk and all later hunks in the file
d - do not commit this hunk or any of the later hunks in the file
s - split the current hunk into smaller hunks
j - leave this hunk undecided, see next hunk
k - leave this hunk undecided, see previous hunk
? - print help
'''


class CLI__Hunk_Prompt(Type_Safe):
    listing : Schema__Hunk_List                       # the hunks as listed
    parts   : Schema__Hunk_List                       # the same files listed with --split (what `s` shows)

    def choose(self) -> list:
        """The chosen hunk ids, in listing order; [] when nothing was chosen or the
        prompt was aborted (end of input)."""
        queue    = [(f, h) for f in self.listing.files for h in f.hunks]
        decided  = {}
        i        = 0
        while 0 <= i < len(queue):
            file, hunk = queue[i]
            hunk_id    = str(hunk.hunk_id)
            keys       = 'y,n,q,a,d' + (',s' if hunk.splittable else '') + ',j,k,?'
            print(f'diff --sgit a/{file.path} b/{file.path}')
            print(str(hunk.header))
            print(str(hunk.text), end='')
            in_file    = [k for k, (f, _) in enumerate(queue) if f is file]
            position   = in_file.index(i) + 1
            try:
                answer = input(f'({position}/{len(in_file)}) Commit this hunk [{keys}]? ').strip().lower()[:1]
            except EOFError:
                print()
                return []
            if answer == 'y':
                decided[hunk_id] = True
                i += 1
            elif answer == 'n':
                decided[hunk_id] = False
                i += 1
            elif answer in ('a', 'd'):
                for k in in_file:
                    if k >= i and str(queue[k][1].hunk_id) not in decided:
                        decided[str(queue[k][1].hunk_id)] = answer == 'a'
                i = in_file[-1] + 1
            elif answer == 's' and hunk.splittable:
                sub = self.sub_hunks(str(file.path), hunk)
                print(f'Split into {len(sub)} hunks.')
                queue[i:i + 1] = [(file, h) for h in sub]
            elif answer == 'j':
                i = min(i + 1, len(queue) - 1) if i + 1 < len(queue) else i
            elif answer == 'k':
                i = max(i - 1, 0)
            elif answer == 'q':
                break
            else:
                print(HELP, end='')
        return [str(h.hunk_id) for _, h in queue if decided.get(str(h.hunk_id))]

    def sub_hunks(self, path: str, hunk) -> list:
        """The --split parts whose change lies inside this hunk."""
        inside = {(int(c.base_start), int(c.base_end)) for c in hunk.changes}
        for f in self.parts.files:
            if str(f.path) == path:
                return [h for h in f.hunks
                        if all((int(c.base_start), int(c.base_end)) in inside for c in h.changes)] or [hunk]
        return [hunk]
