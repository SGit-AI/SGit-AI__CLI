"""Vault__Line_Merge — a three-way line merge that writes what `git merge-file` writes.

Ported from xdiff's xmerge.c (xdl_merge at XDL_MERGE_ZEALOUS_ALNUM, the level
`git merge-file` uses), on the shared Myers differ (Vault__Line_Diff):

1. diff base→ours and base→theirs;
2. walk the two change lists in base order: a change strictly before the other side's
   next one is one-sided; changes that overlap or touch form a conflict, unless they
   are the same change (EAGER); conflicts that touch in ours or theirs coordinates are
   joined (xdl_append_merge);
3. merge style only (diff3 stops at EAGER, as Git does): refine each conflict by
   diffing ours against theirs, so the lines both sides agree on are written once
   (ZEALOUS), then join conflicts at most three lines apart, or separated only by
   lines without a letter or digit (ZEALOUS_ALNUM);
4. write ours' unchanged lines, each one-sided change, and each conflict between
   markers; a side whose last line has no newline gets one before the next marker,
   and marker lines end in CRLF when the surrounding lines do (is_cr_needed).

Positions are xdiff's: i0/chg0 in base, i1/chg1 in ours, i2/chg2 in theirs. The
output is byte-identical to `git merge-file -p` when the two diffs place their hunks
where xdiff places them, which they do whenever the lines are unique (tests compare
against git on every vector). Binary inputs, inputs over the size caps, and diffs past
the differ's cost cap are reported, never merged: the caller falls back to a
whole-file conflict.
"""
import re
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.Vault__Errors                   import Vault__Line_Diff__Too_Different
from   sgit_ai.core.text.Vault__Line_Diff           import Vault__Line_Diff
from   sgit_ai.core.text.Vault__Line_Splitter       import Vault__Line_Splitter
from   sgit_ai.safe_types.Enum__Conflict_Style      import Enum__Conflict_Style
from   sgit_ai.safe_types.Enum__Line_Merge_Outcome  import Enum__Line_Merge_Outcome
from   sgit_ai.schemas.Schema__Conflict_Labels      import Schema__Conflict_Labels
from   sgit_ai.schemas.Schema__Line_Merge_Result    import Schema__Line_Merge_Result

ALNUM           = re.compile(rb'[0-9A-Za-z]')        # xdiff's isalnum() in the C locale
MARKER_SIZE     = 7
MAX_MERGE_BYTES = 8 * 1024 * 1024
MAX_MERGE_LINES = 200_000
CONFLICT        = 0                     # xdmerge_t.mode: 0 conflict, 1 ours, 2 theirs, 4 identical (refined away)
OURS            = 1
THEIRS          = 2
IDENTICAL       = 4


class Vault__Line_Merge(Type_Safe):
    differ   : Vault__Line_Diff
    splitter : Vault__Line_Splitter

    def merge(self, base: bytes, ours: bytes, theirs: bytes, labels: Schema__Conflict_Labels = None,
              conflict_style: Enum__Conflict_Style = None) -> tuple:
        """(merged bytes, Schema__Line_Merge_Result). On BINARY, TOO_LARGE or
        TOO_DIFFERENT the bytes are b'' and nothing is merged."""
        labels = labels or Schema__Conflict_Labels()
        style  = conflict_style or Enum__Conflict_Style.MERGE
        for side in (base, ours, theirs):
            if self.splitter.is_binary(side):
                return b'', Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.BINARY, reason='binary')
            if len(side) > MAX_MERGE_BYTES:
                return b'', Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.TOO_LARGE,
                                                      reason=f'too large for a line merge ({len(side):,} bytes)')
        b_lines, o_lines, t_lines = (self.splitter.split(x) for x in (base, ours, theirs))
        if max(len(b_lines), len(o_lines), len(t_lines)) > MAX_MERGE_LINES:
            return b'', Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.TOO_LARGE,
                                                  reason=f'too many lines for a line merge (over {MAX_MERGE_LINES:,})')
        b_ids, o_ids, t_ids = self.splitter.intern(b_lines, o_lines, t_lines)
        try:
            ours_changes   = self.differ.hunks(b_ids, o_ids)
            theirs_changes = self.differ.hunks(b_ids, t_ids)
            if not ours_changes:                                            # xdl_merge: one side unchanged is the other
                return theirs, Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.CLEAN)
            if not theirs_changes:
                return ours, Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.CLEAN)
            merges = self.do_merge(ours_changes, theirs_changes, o_ids, t_ids, len(b_ids), len(o_ids), len(t_ids))
            if style == Enum__Conflict_Style.MERGE:
                self.refine_conflicts(merges, o_ids, t_ids)
                self.simplify_non_conflicts(merges, o_lines)
        except Vault__Line_Diff__Too_Different as error:
            return b'', Schema__Line_Merge_Result(outcome=Enum__Line_Merge_Outcome.TOO_DIFFERENT, reason=str(error)[:200])
        content   = self.fill(merges, b_lines, o_lines, t_lines, labels, style)
        conflicts = sum(1 for m in merges if m[0] == CONFLICT)
        outcome   = Enum__Line_Merge_Outcome.CONFLICT if conflicts else Enum__Line_Merge_Outcome.CLEAN
        return content, Schema__Line_Merge_Result(outcome=outcome, hunks=conflicts)

    # --- xdl_do_merge -------------------------------------------------------------------

    def do_merge(self, ours_changes: list, theirs_changes: list, o_ids: list, t_ids: list,
                 n_base: int, n_ours: int, n_theirs: int) -> list:
        """The merge list: [mode, i0, chg0, i1, chg1, i2, chg2] entries in order."""
        merges = []
        x1 = [(h[0], h[1] - h[0], h[2], h[3] - h[2]) for h in ours_changes]       # (i1 base, chg1 base, i2 side, chg2 side)
        x2 = [(h[0], h[1] - h[0], h[2], h[3] - h[2]) for h in theirs_changes]
        a = b = 0
        while a < len(x1) and b < len(x2):
            s1, s2 = x1[a], x2[b]
            if s1[0] + s1[1] < s2[0]:                                              # ours strictly before theirs
                self.append(merges, OURS, s1[0], s1[1], s1[2], s1[3], s2[2] - s2[0] + s1[0], s1[1])
                a += 1
                continue
            if s2[0] + s2[1] < s1[0]:                                              # theirs strictly before ours
                self.append(merges, THEIRS, s2[0], s2[1], s1[2] - s1[0] + s2[0], s2[1], s2[2], s2[3])
                b += 1
                continue
            if (s1[0] != s2[0] or s1[1] != s2[1] or s1[3] != s2[3]
                    or o_ids[s1[2]:s1[2] + s1[3]] != t_ids[s2[2]:s2[2] + s2[3]]):   # not the same change: a conflict
                off = s1[0] - s2[0]
                ffo = off + s1[1] - s2[1]
                i0, i1, i2 = s1[0], s1[2], s2[2]
                if off > 0:
                    i0 -= off
                    i1 -= off
                else:
                    i2 += off
                chg0 = s1[0] + s1[1] - i0
                chg1 = s1[2] + s1[3] - i1
                chg2 = s2[2] + s2[3] - i2
                if ffo < 0:
                    chg0 -= ffo
                    chg1 -= ffo
                else:
                    chg2 += ffo
                self.append(merges, CONFLICT, i0, chg0, i1, chg1, i2, chg2)
            end1, end2 = s1[0] + s1[1], s2[0] + s2[1]
            if end1 >= end2:
                b += 1
            if end2 >= end1:
                a += 1
        for s1 in x1[a:]:
            self.append(merges, OURS, s1[0], s1[1], s1[2], s1[3], s1[0] + n_theirs - n_base, s1[1])
        for s2 in x2[b:]:
            self.append(merges, THEIRS, s2[0], s2[1], s2[0] + n_ours - n_base, s2[1], s2[2], s2[3])
        return merges

    def append(self, merges: list, mode: int, i0: int, chg0: int, i1: int, chg1: int, i2: int, chg2: int) -> None:
        """xdl_append_merge: an entry that touches the previous one in ours or theirs
        coordinates joins it, and a join of different kinds is a conflict."""
        if merges:
            m = merges[-1]
            if i1 <= m[3] + m[4] or i2 <= m[5] + m[6]:
                if mode != m[0]:
                    m[0] = CONFLICT
                m[2] = i0 + chg0 - m[1]
                m[4] = i1 + chg1 - m[3]
                m[6] = i2 + chg2 - m[5]
                return
        merges.append([mode, i0, chg0, i1, chg1, i2, chg2])

    # --- ZEALOUS / ZEALOUS_ALNUM -----------------------------------------------------------

    def refine_conflicts(self, merges: list, o_ids: list, t_ids: list) -> None:
        """xdl_refine_conflicts: diff ours against theirs inside each conflict; the lines
        they share are written once, each differing run is its own conflict."""
        k = 0
        while k < len(merges):
            m = merges[k]
            if m[0] != CONFLICT or m[4] == 0 or m[6] == 0:
                k += 1
                continue
            i1, i2 = m[3], m[5]
            hunks  = self.differ.hunks(o_ids[i1:i1 + m[4]], t_ids[i2:i2 + m[6]])
            if not hunks:
                m[0] = IDENTICAL
                k += 1
                continue
            first = hunks[0]
            m[3], m[4], m[5], m[6] = first[0] + i1, first[1] - first[0], first[2] + i2, first[3] - first[2]
            for h in hunks[1:]:
                k += 1
                merges.insert(k, [CONFLICT, m[1], m[2], h[0] + i1, h[1] - h[0], h[2] + i2, h[3] - h[2]])
            k += 1

    def simplify_non_conflicts(self, merges: list, o_lines: list) -> None:
        """xdl_simplify_non_conflicts with simplify_if_no_alnum: two conflicts at most
        three ours lines apart, or apart only by lines without a letter or digit, become
        one conflict that includes the lines between."""
        k = 0
        while k + 1 < len(merges):
            m, n  = merges[k], merges[k + 1]
            begin = m[3] + m[4]
            end   = n[3]
            if m[0] != CONFLICT or n[0] != CONFLICT or (end - begin > 3 and self.contain_alnum(o_lines[begin:end])):
                k += 1
                continue
            m[2] = n[1] + n[2] - m[1]
            m[4] = n[3] + n[4] - m[3]
            m[6] = n[5] + n[6] - m[5]
            del merges[k + 1]

    def contain_alnum(self, lines: list) -> bool:
        return any(ALNUM.search(line) for line in lines)

    # --- xdl_fill_merge_buffer ------------------------------------------------------------

    def fill(self, merges: list, b_lines: list, o_lines: list, t_lines: list,
             labels: Schema__Conflict_Labels, style: Enum__Conflict_Style) -> bytes:
        out = []
        i   = 0
        for m in merges:
            mode = m[0]
            if mode == CONFLICT:
                out.extend(o_lines[i:m[3]])
                eol = b'\r\n' if self.is_cr_needed(b_lines, o_lines, t_lines, m) else b'\n'
                out.append(self.marker(b'<', labels.ours, eol))
                out.extend(self.block(o_lines[m[3]:m[3] + m[4]], eol))
                if style == Enum__Conflict_Style.DIFF3:
                    out.append(self.marker(b'|', labels.base, eol))
                    out.extend(self.block(b_lines[m[1]:m[1] + m[2]], eol))
                out.append(b'=' * MARKER_SIZE + eol)
                out.extend(self.block(t_lines[m[5]:m[5] + m[6]], eol))
                out.append(self.marker(b'>', labels.theirs, eol))
            elif mode & (OURS | THEIRS):
                out.extend(o_lines[i:m[3]])
                if mode & OURS:
                    out.extend(o_lines[m[3]:m[3] + m[4]])
                if mode & THEIRS:
                    out.extend(t_lines[m[5]:m[5] + m[6]])
            else:
                continue                                       # IDENTICAL: ours' lines, copied with what follows
            i = m[3] + m[4]
        out.extend(o_lines[i:])
        return b''.join(out)

    def marker(self, char: bytes, label, eol: bytes) -> bytes:
        text = str(label or '')
        return char * MARKER_SIZE + ((b' ' + text.encode('ascii')) if text else b'') + eol

    def block(self, lines: list, eol: bytes) -> list:
        """A side's lines inside a conflict: a last line without a newline gets one."""
        if lines and not lines[-1].endswith(b'\n'):
            return lines[:-1] + [lines[-1] + eol]
        return lines

    def is_cr_needed(self, b_lines: list, o_lines: list, t_lines: list, m: list) -> bool:
        needs_cr = self.is_eol_crlf(o_lines, m[3] - 1 if m[3] else 0)
        if needs_cr:
            needs_cr = self.is_eol_crlf(t_lines, m[5] - 1 if m[5] else 0)
        if needs_cr:
            needs_cr = self.is_eol_crlf(b_lines, 0)
        return needs_cr is True

    def is_eol_crlf(self, lines: list, i: int):
        """True / False, or -1 when the file cannot tell (xdiff's tri-state)."""
        if i < len(lines) - 1:
            return len(lines[i]) > 1 and lines[i].endswith(b'\r\n')
        if not lines:
            return -1
        if lines[i].endswith(b'\n'):
            return lines[i].endswith(b'\r\n')
        if i == 0:
            return -1
        return lines[i - 1].endswith(b'\r\n')
