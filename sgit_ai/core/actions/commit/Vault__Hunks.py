"""Vault__Hunks — the hunks of `sgit commit -p / --list-hunks / --hunk` (design__03 §5.3).

Pure: bytes in, schemas and bytes out. The changes come from the shared line differ
(Vault__Line_Diff: Myers with Git's change compaction, so a hunk's edges are where
`git diff` puts them), grouped into hunks as xdiff does: two changes share a hunk
when at most 2 x context equal lines separate them. Lines keep their endings, so CRLF
and a missing final newline survive a partial commit byte for byte.

A hunk's id is derived from what it changes (path, base content, position, removed
and added lines), never from its position in a list: an id listed before the file
changed cannot select a different hunk afterwards, it just no longer exists.
Binary files, files over `max_bytes`, unrelated rewrites past the differ's cost cap,
new files and deleted files are one whole-file hunk.
"""
import hashlib
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.Vault__Errors                   import Vault__Line_Diff__Too_Different
from   sgit_ai.core.text.Vault__Line_Diff           import Vault__Line_Diff
from   sgit_ai.core.text.Vault__Line_Splitter       import Vault__Line_Splitter
from   sgit_ai.safe_types.Enum__Hunk_File_Status    import Enum__Hunk_File_Status
from   sgit_ai.safe_types.Safe_UInt__Byte_Size      import Safe_UInt__Byte_Size
from   sgit_ai.safe_types.Safe_UInt__Line_Number    import Safe_UInt__Line_Number
from   sgit_ai.schemas.Schema__Line_Hunk            import Schema__Line_Hunk
from   sgit_ai.schemas.commit.Schema__File_Hunks    import Schema__File_Hunks
from   sgit_ai.schemas.commit.Schema__Hunk          import Schema__Hunk

CONTEXT_LINES   = 3                                   # git diff -U3
MAX_HUNK_BYTES  = 8 * 1024 * 1024                     # the line merge's cap; above it, whole-file only
FUNCNAME_BYTES  = 80                                  # xdiff's funcname buffer
NO_NEWLINE      = '\\ No newline at end of file\n'


class Vault__Hunks(Type_Safe):
    context   : Safe_UInt__Line_Number = CONTEXT_LINES
    max_bytes : Safe_UInt__Byte_Size   = MAX_HUNK_BYTES

    def hunks_of(self, path: str, base, work, base_hash: str = '', work_hash: str = '',
                 split: bool = False) -> Schema__File_Hunks:
        """base / work: bytes, or None when the file is absent on that side."""
        splitter = Vault__Line_Splitter()
        status   = (Enum__Hunk_File_Status.ADDED   if base is None else
                    Enum__Hunk_File_Status.DELETED if work is None else Enum__Hunk_File_Status.MODIFIED)
        binary   = any(side is not None and splitter.is_binary(side) for side in (base, work))
        result   = Schema__File_Hunks(path=path, status=status, binary=binary, base_hash=base_hash, work_hash=work_hash)
        too_big  = any(side is not None and len(side) > int(self.max_bytes) for side in (base, work))
        if status != Enum__Hunk_File_Status.MODIFIED or binary or too_big:
            result.hunks.append(self.whole_file_hunk(path, base, work, base_hash, work_hash, binary))
            return result
        a, b = splitter.split(base), splitter.split(work)
        try:
            changes = self.changes(a, b)
        except Vault__Line_Diff__Too_Different:
            result.hunks.append(self.whole_file_hunk(path, base, work, base_hash, work_hash, binary))
            return result
        groups = self.group(changes)
        if split:
            groups = [[change] for group in groups for change in group]
        for number, group in enumerate(groups, start=1):
            result.hunks.append(self.hunk(path, base_hash, a, b, group, number, splittable=len(group) > 1))
        return result

    def changes(self, a: list, b: list) -> list:
        a_ids, b_ids = Vault__Line_Splitter().intern(a, b)
        return Vault__Line_Diff().hunks(a_ids, b_ids, a, b)              # [(a_lo, a_hi, b_lo, b_hi)], placed as git diff places them

    def group(self, changes: list) -> list:
        """xdl_get_hunk: a change joins the previous hunk when the equal run between
        them is at most 2 x context lines."""
        groups = []
        for change in changes:
            if groups and change[0] - groups[-1][-1][1] <= 2 * int(self.context):
                groups[-1].append(change)
            else:
                groups.append([change])
        return groups

    def hunk(self, path: str, base_hash: str, a: list, b: list, group: list, number: int,
             splittable: bool) -> Schema__Hunk:
        ctx      = int(self.context)
        first    = group[0]
        last     = group[-1]
        a_start  = max(first[0] - ctx, 0)
        b_start  = max(first[2] - ctx, 0)
        a_end    = min(last[1] + ctx, len(a))
        b_end    = min(last[3] + ctx, len(b))
        removed  = [line for c in group for line in a[c[0]:c[1]]]
        added    = [line for c in group for line in b[c[2]:c[3]]]
        body, i  = [], a_start
        for a_lo, a_hi, b_lo, b_hi in group:
            body += [(' ', line) for line in a[i:a_lo]]
            body += [('-', line) for line in a[a_lo:a_hi]]
            body += [('+', line) for line in b[b_lo:b_hi]]
            i     = a_hi
        body    += [(' ', line) for line in a[i:a_end]]
        old_lines, new_lines = a_end - a_start, b_end - b_start
        header   = (f'@@ -{self.range_text(a_start, old_lines)} +{self.range_text(b_start, new_lines)} @@'
                    + self.funcname(a, a_start))
        return Schema__Hunk(hunk_id    = self.hunk_id(path, base_hash, a_start + 1, old_lines, removed, added),
                            index      = number,
                            old_start  = a_start + 1 if old_lines else a_start,
                            old_lines  = old_lines,
                            new_start  = b_start + 1 if new_lines else b_start,
                            new_lines  = new_lines,
                            added      = len(added),
                            removed    = len(removed),
                            header     = header,
                            text       = self.display(body),
                            splittable = splittable,
                            changes    = [Schema__Line_Hunk(base_start=c[0], base_end=c[1], side_start=c[2], side_end=c[3])
                                          for c in group])

    def whole_file_hunk(self, path: str, base, work, base_hash: str, work_hash: str, binary: bool) -> Schema__Hunk:
        splitter = Vault__Line_Splitter()
        a        = splitter.split(base) if base is not None and not binary else []
        b        = splitter.split(work) if work is not None and not binary else []
        if binary:
            text = 'Binary file differs\n'
        elif len(a) + len(b) > 2000:
            text = f'(whole file: {len(a)} line(s) -> {len(b)} line(s))\n'
        else:
            text = self.display([('-', line) for line in a] + [('+', line) for line in b])
        digest = hashlib.sha256(b'\0'.join([path.encode(), base_hash.encode(), b'whole', work_hash.encode()])).hexdigest()
        return Schema__Hunk(hunk_id    = f'h-{digest[:12]}',
                            index      = 1,
                            old_start  = 1 if a else 0, old_lines = len(a),
                            new_start  = 1 if b else 0, new_lines = len(b),
                            removed    = len(a), added = len(b),
                            header     = 'whole file' + (' (binary)' if binary else ''),
                            text       = text,
                            whole_file = True)

    def hunk_id(self, path: str, base_hash: str, old_start: int, old_lines: int, removed: list, added: list) -> str:
        digest = hashlib.sha256(b'\0'.join([path.encode(), base_hash.encode(), str(old_start).encode(),
                                            str(old_lines).encode(), b''.join(removed), b''.join(added)])).hexdigest()
        return f'h-{digest[:12]}'

    def range_text(self, start: int, count: int) -> str:
        """xdl_emit_hunk_hdr: `s,c`, `s` alone when c is 1, and the line before when c is 0."""
        first = start + 1 if count else start
        return str(first) if count == 1 else f'{first},{count}'

    def funcname(self, a: list, a_start: int) -> str:
        """Git's default funcname: the nearest line above the hunk that starts with a
        letter, `_` or `$` (display only)."""
        for line in reversed(a[:a_start]):
            if line[:1].isalpha() or line[:1] in (b'_', b'$'):
                return ' ' + line[:FUNCNAME_BYTES].decode('utf-8', 'replace').rstrip()
        return ''

    def display(self, body: list) -> str:
        out = []
        for sign, line in body:
            text = line.decode('utf-8', 'replace')
            text = ''.join(ch if ch in '\t\r\n' or ch >= ' ' and ch != '\x7f' else '?' for ch in text)
            out.append(sign + text if text.endswith('\n') else sign + text + '\n' + NO_NEWLINE)
        return ''.join(out)

    # --- applying ---------------------------------------------------------------------------

    def apply(self, base, work, hunks: list, chosen_ids: set):
        """The file with only the chosen hunks applied to base: bytes, or None when the
        result is "no file" (a new file not chosen, a deletion chosen). `hunks` may mix a
        file's hunks and their split parts (both listings' ids select); every chosen
        change is one of the same differ run's changes, so they never overlap."""
        if any(h.whole_file for h in hunks):
            return work if any(str(h.hunk_id) in chosen_ids for h in hunks) else base
        splitter    = Vault__Line_Splitter()
        a, b        = splitter.split(base), splitter.split(work)
        all_changes = sorted({self.change_tuple(c) for h in hunks for c in h.changes})
        chosen      = {self.change_tuple(c) for h in hunks if str(h.hunk_id) in chosen_ids for c in h.changes}
        out, i      = [], 0
        for a_lo, a_hi, b_lo, b_hi in all_changes:
            out += a[i:a_lo]
            out += b[b_lo:b_hi] if (a_lo, a_hi, b_lo, b_hi) in chosen else a[a_lo:a_hi]
            i    = a_hi
        out += a[i:]
        return b''.join(out)

    def change_tuple(self, change) -> tuple:
        return int(change.base_start), int(change.base_end), int(change.side_start), int(change.side_end)
