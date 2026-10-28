"""Vault__Line_Diff — the one line differ (design__00 F1), for merge, blame and diff.

A port of Git's xdiff (xdl_do_diff, then xdl_change_compact): Myers 1986, "An O(ND)
Difference Algorithm", in xdiff's linear-space form with its pre-pass and
heuristics, so that changes land where Git puts them, repeated lines included.
Changed lines are marked on each side and read back as hunks. An explicit stack
replaces recursion (a 5,000-line edit would pass Python's recursion limit).
Memory is O(N + M).

A cost cap stops a diff of two unrelated files early with
Vault__Line_Diff__Too_Different: the caller falls back to whole-file handling.

Inputs are lists of ints from Vault__Line_Splitter.intern, so equal lines compare
as equal ints, with or without whitespace folded.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.Vault__Errors                   import Vault__Line_Diff__Too_Different
from   sgit_ai.safe_types.Safe_UInt__Line_Number    import Safe_UInt__Line_Number
from   sgit_ai.schemas.Schema__Line_Hunk            import Schema__Line_Hunk

MAX_EDIT_COST  = 5000                                  # lines added + removed
MAX_EQLIMIT    = 1024                                  # xdiff's XDL_MAX_EQLIMIT
SIMSCAN_WINDOW = 100                                   # XDL_SIMSCAN_WINDOW
KPDIS_RUN      = 4                                     # XDL_KPDIS_RUN
MAX_COST_MIN   = 256                                   # XDL_MAX_COST_MIN
SNAKE_CNT      = 20                                    # XDL_SNAKE_CNT
HEUR_MIN_COST  = 256                                   # XDL_HEUR_MIN_COST
K_HEUR         = 4                                     # XDL_K_HEUR
LINE_MAX       = 2 ** 62                               # XDL_LINE_MAX

MAX_INDENT                         = 200               # the indent heuristic's constants, as in xdiffi.c
MAX_BLANKS                         = 20
INDENT_MAX_SLIDING                 = 100
START_OF_FILE_PENALTY              = 1
END_OF_FILE_PENALTY                = 21
TOTAL_BLANK_WEIGHT                 = -30
POST_BLANK_WEIGHT                  = 6
RELATIVE_INDENT_PENALTY            = -4
RELATIVE_INDENT_WITH_BLANK_PENALTY = 10
RELATIVE_OUTDENT_PENALTY           = 24
RELATIVE_OUTDENT_WITH_BLANK_PENALTY = 17
RELATIVE_DEDENT_PENALTY            = 23
RELATIVE_DEDENT_WITH_BLANK_PENALTY = 17
INDENT_WEIGHT                      = 60
WHITESPACE                         = frozenset(b' \t\n\r\v\f')        # XDL_ISSPACE


class Vault__Line_Diff(Type_Safe):
    max_edit_cost : Safe_UInt__Line_Number = MAX_EDIT_COST

    def diff(self, a_ids: list, b_ids: list) -> list:
        """list[Schema__Line_Hunk], sorted by base_start: the changed regions taking
        a (the base) to b (the side)."""
        return [Schema__Line_Hunk(base_start=h[0], base_end=h[1], side_start=h[2], side_end=h[3])
                for h in self.hunks(a_ids, b_ids)]

    def hunks(self, a_ids: list, b_ids: list, a_text: list = None, b_text: list = None) -> list:
        """The same hunks as plain (base_start, base_end, side_start, side_end) tuples:
        the hot path for callers that diff many file pairs (blame). With the lines' text
        (`a_text`, `b_text`: the lines as bytes, newline included), Git's indent heuristic
        places a change that could sit at several places, as `git diff` and `git blame`
        do (diff.indentHeuristic, on by default); `git merge-file` does not use it."""
        changed_a, changed_b = self.mark_changes(a_ids, b_ids)
        self.compact(a_ids, changed_a, changed_b, a_text)
        self.compact(b_ids, changed_b, changed_a, b_text)
        hunks = []
        i, j, n, m = 0, 0, len(a_ids), len(b_ids)
        while i < n or j < m:
            if i < n and j < m and not changed_a[i] and not changed_b[j]:
                i += 1
                j += 1
                continue
            start_i, start_j = i, j
            while i < n and changed_a[i]:
                i += 1
            while j < m and changed_b[j]:
                j += 1
            hunks.append((start_i, i, start_j, j))
        return hunks

    def opcodes(self, a_ids: list, b_ids: list, a_text: list = None, b_text: list = None) -> list:
        """difflib.SequenceMatcher.get_opcodes() shape: (tag, i1, i2, j1, j2) with tag in
        equal / replace / delete / insert, covering both sequences."""
        ops, i, j = [], 0, 0
        for a_lo, a_hi, b_lo, b_hi in self.hunks(a_ids, b_ids, a_text, b_text):
            if a_lo > i:
                ops.append(('equal', i, a_lo, j, b_lo))
            tag = 'replace' if a_hi > a_lo and b_hi > b_lo else ('delete' if a_hi > a_lo else 'insert')
            ops.append((tag, a_lo, a_hi, b_lo, b_hi))
            i, j = a_hi, b_hi
        if i < len(a_ids) or j < len(b_ids):
            ops.append(('equal', i, len(a_ids), j, len(b_ids)))
        return ops

    def matching_blocks(self, a_ids: list, b_ids: list) -> list:
        """difflib shape: (i, j, size) runs of equal lines, ascending, ending with the
        (len(a), len(b), 0) sentinel. The sizes add up to the LCS length."""
        blocks = [(i1, j1, i2 - i1) for tag, i1, i2, j1, j2 in self.opcodes(a_ids, b_ids) if tag == 'equal' and i2 > i1]
        blocks.append((len(a_ids), len(b_ids), 0))
        return blocks

    def mark_changes(self, a: list, b: list) -> tuple:
        """Two lists of bools: which lines of a are deleted and which of b are inserted,
        placed where Git's xdiff places them (xdl_do_diff without XDF_NEED_MINIMAL):

        1. xdl_trim_ends: the common prefix and suffix are unchanged.
        2. xdl_cleanup_records: a line with no match on the other side is changed before
           any search; a line that occurs often on the other side (at least
           bogosqrt(lines), at most 1,024 times) is changed too when it sits inside a run
           of such lines (xdl_clean_mmatch). The search runs on what is left.
        3. xdl_recs_cmp / xdl_split: divide and conquer on the middle snake, with xdiff's
           tie-breaks and its cost heuristics (a snake of 20, a cost of 256, the
           furthest-reaching path past bogosqrt of the size).

        On unique lines this is a shortest edit script, like any Myers diff. On repeated
        lines (`}`, blank lines) several placements are equally short and Git's choice is
        the one users and `git merge-file` expect (cli.build BR-2, BR-3)."""
        changed_a = [False] * len(a)
        changed_b = [False] * len(b)
        dstart, end_a, end_b = self.trim_ends(a, b)
        kept_a, kept_b = self.cleanup_records(a, b, dstart, end_a, end_b, changed_a, changed_b)
        self.recs_cmp([a[i] for i in kept_a], kept_a, changed_a, [b[i] for i in kept_b], kept_b, changed_b)
        cost = changed_a.count(True) + changed_b.count(True)
        if cost > int(self.max_edit_cost):
            raise Vault__Line_Diff__Too_Different(cost, int(self.max_edit_cost))
        return changed_a, changed_b

    def trim_ends(self, a: list, b: list) -> tuple:
        """xdl_trim_ends: (first differing line, end of a's middle, end of b's middle)."""
        n, m, i = len(a), len(b), 0
        lim = min(n, m)
        while i < lim and a[i] == b[i]:
            i += 1
        k = 0
        while k < lim - i and a[n - 1 - k] == b[m - 1 - k]:
            k += 1
        return i, n - k, m - k

    def bogosqrt(self, n: int) -> int:
        """xdl_bogosqrt: the power of two near sqrt(n), as xdiff computes it."""
        i = 1
        while n > 0:
            i <<= 1
            n >>= 2
        return i

    def cleanup_records(self, a: list, b: list, dstart: int, end_a: int, end_b: int,
                        changed_a: list, changed_b: list) -> tuple:
        """xdl_cleanup_records: the line indexes left for the search, per side; the
        lines it drops are marked changed. Occurrences are counted over whole files."""
        count_a, count_b = {}, {}
        for x in a:
            count_a[x] = count_a.get(x, 0) + 1
        for x in b:
            count_b[x] = count_b.get(x, 0) + 1
        kept = []
        for lines, other, changed, end in ((a, count_b, changed_a, end_a), (b, count_a, changed_b, end_b)):
            mlim = min(self.bogosqrt(len(lines)), MAX_EQLIMIT)
            dis  = {}
            for i in range(dstart, end):
                nm     = other.get(lines[i], 0)
                dis[i] = 0 if nm == 0 else (2 if nm >= mlim else 1)
            side = []
            for i in range(dstart, end):
                if dis[i] == 1 or (dis[i] == 2 and not self.clean_mmatch(dis, i, dstart, end - 1)):
                    side.append(i)
                else:
                    changed[i] = True
            kept.append(side)
        return kept[0], kept[1]

    def clean_mmatch(self, dis: dict, i: int, s: int, e: int) -> bool:
        """xdl_clean_mmatch: True drops line i, a frequent line inside a run of lines
        that have no match (looked at up to 100 lines away on each side)."""
        s = max(s, i - SIMSCAN_WINDOW)
        e = min(e, i + SIMSCAN_WINDOW)
        r, rdis0, rpdis0 = 1, 0, 1
        while i - r >= s:
            if dis[i - r] == 0:
                rdis0 += 1
            elif dis[i - r] == 2:
                rpdis0 += 1
            else:
                break
            r += 1
        if rdis0 == 0:
            return False
        r, rdis1, rpdis1 = 1, 0, 1
        while i + r <= e:
            if dis[i + r] == 0:
                rdis1 += 1
            elif dis[i + r] == 2:
                rpdis1 += 1
            else:
                break
            r += 1
        if rdis1 == 0:
            return False
        rdis1  += rdis0
        rpdis1 += rpdis0
        return rpdis1 * KPDIS_RUN < rpdis1 + rdis1

    def recs_cmp(self, ha1: list, rindex1: list, rchg1: list, ha2: list, rindex2: list, rchg2: list) -> None:
        """xdl_recs_cmp over the lines cleanup_records left, with an explicit stack."""
        n1, n2   = len(ha1), len(ha2)
        ndiags   = n1 + n2 + 3
        base     = n2 + 1
        kvdf     = [0] * ndiags
        kvdb     = [0] * ndiags
        mxcost   = max(self.bogosqrt(ndiags), MAX_COST_MIN)
        stack    = [(0, n1, 0, n2, False)]
        while stack:
            off1, lim1, off2, lim2, need_min = stack.pop()
            while off1 < lim1 and off2 < lim2 and ha1[off1] == ha2[off2]:
                off1 += 1
                off2 += 1
            while off1 < lim1 and off2 < lim2 and ha1[lim1 - 1] == ha2[lim2 - 1]:
                lim1 -= 1
                lim2 -= 1
            if off1 == lim1:
                for k in range(off2, lim2):
                    rchg2[rindex2[k]] = True
            elif off2 == lim2:
                for k in range(off1, lim1):
                    rchg1[rindex1[k]] = True
            else:
                i1, i2, min_lo, min_hi = self.split(ha1, off1, lim1, ha2, off2, lim2, kvdf, kvdb, base,
                                                    need_min, mxcost)
                stack.append((i1, lim1, i2, lim2, min_hi))
                stack.append((off1, i1, off2, i2, min_lo))

    def split(self, ha1: list, off1: int, lim1: int, ha2: list, off2: int, lim2: int,
              kvdf: list, kvdb: list, base: int, need_min: bool, mxcost: int) -> tuple:
        """xdl_split: (i1, i2, min_lo, min_hi), the point to divide at and whether each
        half must be searched for a minimal script. kvdf / kvdb are indexed by diagonal
        (base + d)."""
        dmin, dmax = off1 - lim2, lim1 - off2
        fmid, bmid = off1 - off2, lim1 - lim2
        odd        = (fmid - bmid) & 1
        fmin = fmax = fmid
        bmin = bmax = bmid
        kvdf[base + fmid] = off1
        kvdb[base + bmid] = lim1
        ec = 0
        while True:
            ec += 1
            got_snake = False
            if fmin > dmin:
                fmin -= 1
                kvdf[base + fmin - 1] = -1
            else:
                fmin += 1
            if fmax < dmax:
                fmax += 1
                kvdf[base + fmax + 1] = -1
            else:
                fmax -= 1
            for d in range(fmax, fmin - 1, -2):
                if kvdf[base + d - 1] >= kvdf[base + d + 1]:
                    i1 = kvdf[base + d - 1] + 1
                else:
                    i1 = kvdf[base + d + 1]
                prev1 = i1
                i2    = i1 - d
                while i1 < lim1 and i2 < lim2 and ha1[i1] == ha2[i2]:
                    i1 += 1
                    i2 += 1
                if i1 - prev1 > SNAKE_CNT:
                    got_snake = True
                kvdf[base + d] = i1
                if odd and bmin <= d <= bmax and kvdb[base + d] <= i1:
                    return i1, i2, True, True
            if bmin > dmin:
                bmin -= 1
                kvdb[base + bmin - 1] = LINE_MAX
            else:
                bmin += 1
            if bmax < dmax:
                bmax += 1
                kvdb[base + bmax + 1] = LINE_MAX
            else:
                bmax -= 1
            for d in range(bmax, bmin - 1, -2):
                if kvdb[base + d - 1] < kvdb[base + d + 1]:
                    i1 = kvdb[base + d - 1]
                else:
                    i1 = kvdb[base + d + 1] - 1
                prev1 = i1
                i2    = i1 - d
                while i1 > off1 and i2 > off2 and ha1[i1 - 1] == ha2[i2 - 1]:
                    i1 -= 1
                    i2 -= 1
                if prev1 - i1 > SNAKE_CNT:
                    got_snake = True
                kvdb[base + d] = i1
                if not odd and fmin <= d <= fmax and i1 <= kvdf[base + d]:
                    return i1, i2, True, True
            if need_min:
                continue
            if got_snake and ec > HEUR_MIN_COST:
                found = self.heuristic_split(ha1, off1, lim1, ha2, off2, lim2, kvdf, kvdb, base, ec,
                                             fmin, fmax, fmid, bmin, bmax, bmid)
                if found:
                    return found
            if ec >= mxcost:
                return self.furthest_split(off1, lim1, off2, lim2, kvdf, kvdb, base, fmin, fmax, bmin, bmax)

    def heuristic_split(self, ha1, off1, lim1, ha2, off2, lim2, kvdf, kvdb, base, ec,
                        fmin, fmax, fmid, bmin, bmax, bmid):
        """xdl_split's sampling of "interesting" diagonals past a cost of 256 (XDL_K_HEUR)."""
        best, at = 0, None
        for d in range(fmax, fmin - 1, -2):
            dd = d - fmid if d > fmid else fmid - d
            i1 = kvdf[base + d]
            i2 = i1 - d
            v  = (i1 - off1) + (i2 - off2) - dd
            if v > K_HEUR * ec and v > best and off1 + SNAKE_CNT <= i1 < lim1 and off2 + SNAKE_CNT <= i2 < lim2:
                k = 1
                while ha1[i1 - k] == ha2[i2 - k]:
                    if k == SNAKE_CNT:
                        best, at = v, (i1, i2)
                        break
                    k += 1
        if best > 0:
            return at[0], at[1], True, False
        best, at = 0, None
        for d in range(bmax, bmin - 1, -2):
            dd = d - bmid if d > bmid else bmid - d
            i1 = kvdb[base + d]
            i2 = i1 - d
            v  = (lim1 - i1) + (lim2 - i2) - dd
            if v > K_HEUR * ec and v > best and off1 < i1 <= lim1 - SNAKE_CNT and off2 < i2 <= lim2 - SNAKE_CNT:
                k = 0
                while ha1[i1 + k] == ha2[i2 + k]:
                    if k == SNAKE_CNT - 1:
                        best, at = v, (i1, i2)
                        break
                    k += 1
        if best > 0:
            return at[0], at[1], False, True
        return None

    def furthest_split(self, off1, lim1, off2, lim2, kvdf, kvdb, base, fmin, fmax, bmin, bmax) -> tuple:
        """xdl_split past the cost limit: the furthest-reaching path, forward or back."""
        fbest = fbest1 = -1
        for d in range(fmax, fmin - 1, -2):
            i1 = min(kvdf[base + d], lim1)
            i2 = i1 - d
            if lim2 < i2:
                i1, i2 = lim2 + d, lim2
            if fbest < i1 + i2:
                fbest, fbest1 = i1 + i2, i1
        bbest = bbest1 = LINE_MAX
        for d in range(bmax, bmin - 1, -2):
            i1 = max(off1, kvdb[base + d])
            i2 = i1 - d
            if i2 < off2:
                i1, i2 = off2 + d, off2
            if i1 + i2 < bbest:
                bbest, bbest1 = i1 + i2, i1
        if (lim1 + lim2) - bbest < fbest - (off1 + off2):
            return fbest1, fbest - fbest1, True, False
        return bbest1, bbest - bbest1, False, True

    def compact(self, lines: list, changed: list, other: list, text: list = None) -> None:
        """xdiff's xdl_change_compact: every group of changed lines that can slide (a
        change of `x` inside `x x x` can sit anywhere) is slid as far up as it goes, then as
        far down, merging with groups it touches, and then back up to the last place where
        it lines up with a change in the other file. Failing that, with the lines' `text`,
        the indent heuristic picks the place (XDF_INDENT_HEURISTIC). Git does this to both
        files before building a diff or a merge, so ambiguous changes land where Git puts
        them. `changed` and `other` are the two files' marks, in step."""
        n, m = len(changed), len(other)

        def flag(marks, i):
            return 0 <= i < len(marks) and marks[i]

        def extend(marks, start, end):
            while flag(marks, end):
                end += 1
            return end

        def group_next(marks, g):
            if g[1] >= len(marks):
                return False
            g[0] = g[1] + 1
            g[1] = extend(marks, g[0], g[0])
            return True

        def group_previous(marks, g):
            if g[0] == 0:
                return False
            g[1] = g[0] - 1
            g[0] = g[1]
            while flag(marks, g[0] - 1):
                g[0] -= 1
            return True

        def slide_down(g):
            if g[1] < n and lines[g[0]] == lines[g[1]]:
                changed[g[0]] = False
                changed[g[1]] = True
                g[0] += 1
                g[1] = extend(changed, g[1] + 1, g[1] + 1)
                return True
            return False

        def slide_up(g):
            if g[0] > 0 and lines[g[0] - 1] == lines[g[1] - 1]:
                g[0] -= 1
                g[1] -= 1
                changed[g[0]] = True
                changed[g[1]] = False
                while flag(changed, g[0] - 1):
                    g[0] -= 1
                return True
            return False

        g  = [0, extend(changed, 0, 0)]
        go = [0, extend(other,   0, 0)]
        while True:
            if g[1] != g[0]:
                while True:
                    size               = g[1] - g[0]
                    end_matching_other = -1
                    while slide_up(g):
                        group_previous(other, go)
                    earliest_end = g[1]
                    if go[1] > go[0]:
                        end_matching_other = g[1]
                    while slide_down(g):
                        group_next(other, go)
                        if go[1] > go[0]:
                            end_matching_other = g[1]
                    if size == g[1] - g[0]:
                        break
                if g[1] == earliest_end:
                    pass                                                     # it cannot move
                elif end_matching_other != -1:
                    while go[1] == go[0]:
                        slide_up(g)
                        group_previous(other, go)
                elif text is not None:
                    best_shift = self.best_shift(text, earliest_end, g[1], size)
                    while g[1] > best_shift:
                        slide_up(g)
                        group_previous(other, go)
            if not group_next(changed, g):
                break
            group_next(other, go)

    # --- the indent heuristic (xdiff's measure_split, score_add_split, score_cmp) ----------

    def best_shift(self, text: list, earliest_end: int, end: int, size: int) -> int:
        """The end of the group's best place among the last ones it can reach (at most
        its own size + 1, and 100, back from the lowest): the lowest score wins, a later
        place on a tie."""
        shift = max(earliest_end, end - size - 1, end - INDENT_MAX_SLIDING)
        best, best_score = -1, None
        while shift <= end:
            score = [0, 0]                                                   # effective indent, penalty
            self.score_add_split(self.measure_split(text, shift), score)
            self.score_add_split(self.measure_split(text, shift - size), score)
            if best == -1 or self.score_cmp(score, best_score) <= 0:
                best, best_score = shift, score
            shift += 1
        return best

    def get_indent(self, line) -> int:
        """Columns of leading whitespace (a tab to the next multiple of 8, at most 200);
        -1 for a line that is all whitespace."""
        if isinstance(line, str):
            line = line.encode('utf-8', 'surrogateescape')
        ret = 0
        for c in line:
            if c not in WHITESPACE:
                return ret
            if c == 0x20:
                ret += 1
            elif c == 0x09:
                ret += 8 - ret % 8
            if ret >= MAX_INDENT:
                return MAX_INDENT
        return -1

    def measure_split(self, text: list, split: int) -> dict:
        n = len(text)
        m = dict(end_of_file=split >= n, indent=-1 if split >= n else self.get_indent(text[split]),
                 pre_blank=0, pre_indent=-1, post_blank=0, post_indent=-1)
        for i in range(split - 1, -1, -1):
            m['pre_indent'] = self.get_indent(text[i])
            if m['pre_indent'] != -1:
                break
            m['pre_blank'] += 1
            if m['pre_blank'] == MAX_BLANKS:
                m['pre_indent'] = 0
                break
        for i in range(split + 1, n):
            m['post_indent'] = self.get_indent(text[i])
            if m['post_indent'] != -1:
                break
            m['post_blank'] += 1
            if m['post_blank'] == MAX_BLANKS:
                m['post_indent'] = 0
                break
        return m

    def score_add_split(self, m: dict, score: list) -> None:
        if m['pre_indent'] == -1 and m['pre_blank'] == 0:
            score[1] += START_OF_FILE_PENALTY
        if m['end_of_file']:
            score[1] += END_OF_FILE_PENALTY
        post_blank  = 1 + m['post_blank'] if m['indent'] == -1 else 0
        total_blank = m['pre_blank'] + post_blank
        score[1]   += TOTAL_BLANK_WEIGHT * total_blank + POST_BLANK_WEIGHT * post_blank
        indent      = m['indent'] if m['indent'] != -1 else m['post_indent']
        any_blanks  = total_blank != 0
        score[0]   += indent
        if indent == -1 or m['pre_indent'] == -1 or indent == m['pre_indent']:
            return
        if indent > m['pre_indent']:
            score[1] += RELATIVE_INDENT_WITH_BLANK_PENALTY if any_blanks else RELATIVE_INDENT_PENALTY
        elif m['post_indent'] != -1 and m['post_indent'] > indent:
            score[1] += RELATIVE_OUTDENT_WITH_BLANK_PENALTY if any_blanks else RELATIVE_OUTDENT_PENALTY
        else:
            score[1] += RELATIVE_DEDENT_WITH_BLANK_PENALTY if any_blanks else RELATIVE_DEDENT_PENALTY

    def score_cmp(self, s1: list, s2: list) -> int:
        cmp_indents = (s1[0] > s2[0]) - (s1[0] < s2[0])
        return INDENT_WEIGHT * cmp_indents + (s1[1] - s2[1])
