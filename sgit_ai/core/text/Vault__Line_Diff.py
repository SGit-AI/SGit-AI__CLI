"""Vault__Line_Diff — the one line differ (design__00 F1), for merge, blame and diff.

Myers 1986, "An O(ND) Difference Algorithm", the linear-space variant: trim the
common prefix and suffix, then find the middle snake of the rest and split there,
until every range is a pure insertion or deletion. Changed lines are marked on
each side and read back as hunks. An explicit stack replaces recursion (a 5,000-
line edit would pass Python's recursion limit). Memory is O(N + M).

A cost cap stops a diff of two unrelated files early with
Vault__Line_Diff__Too_Different: the caller falls back to whole-file handling.

Inputs are lists of ints from Vault__Line_Splitter.intern, so equal lines compare
as equal ints, with or without whitespace folded.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.Vault__Errors                   import Vault__Line_Diff__Too_Different
from   sgit_ai.safe_types.Safe_UInt__Line_Number    import Safe_UInt__Line_Number
from   sgit_ai.schemas.Schema__Line_Hunk            import Schema__Line_Hunk

MAX_EDIT_COST = 5000                                   # lines added + removed


class Vault__Line_Diff(Type_Safe):
    max_edit_cost : Safe_UInt__Line_Number = MAX_EDIT_COST

    def diff(self, a_ids: list, b_ids: list) -> list:
        """list[Schema__Line_Hunk], sorted by base_start: the changed regions taking
        a (the base) to b (the side)."""
        return [Schema__Line_Hunk(base_start=h[0], base_end=h[1], side_start=h[2], side_end=h[3])
                for h in self.hunks(a_ids, b_ids)]

    def hunks(self, a_ids: list, b_ids: list) -> list:
        """The same hunks as plain (base_start, base_end, side_start, side_end) tuples:
        the hot path for callers that diff many file pairs (blame)."""
        changed_a, changed_b = self.mark_changes(a_ids, b_ids)
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

    def opcodes(self, a_ids: list, b_ids: list) -> list:
        """difflib.SequenceMatcher.get_opcodes() shape: (tag, i1, i2, j1, j2) with tag in
        equal / replace / delete / insert, covering both sequences."""
        ops, i, j = [], 0, 0
        for a_lo, a_hi, b_lo, b_hi in self.hunks(a_ids, b_ids):
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
        """Two lists of bools: which lines of a are deleted and which of b are inserted
        on one shortest edit script."""
        changed_a = [False] * len(a)
        changed_b = [False] * len(b)
        limit     = int(self.max_edit_cost)
        stack     = [(0, len(a), 0, len(b))]
        while stack:
            a_lo, a_hi, b_lo, b_hi = stack.pop()
            while a_lo < a_hi and b_lo < b_hi and a[a_lo] == b[b_lo]:                # common prefix
                a_lo += 1
                b_lo += 1
            while a_lo < a_hi and b_lo < b_hi and a[a_hi - 1] == b[b_hi - 1]:        # common suffix
                a_hi -= 1
                b_hi -= 1
            if a_lo == a_hi or b_lo == b_hi:
                for k in range(a_lo, a_hi):
                    changed_a[k] = True
                for k in range(b_lo, b_hi):
                    changed_b[k] = True
                continue
            split = self.middle_snake(a, a_lo, a_hi, b, b_lo, b_hi, limit)
            if split is None or split in ((a_lo, b_lo), (a_hi, b_hi)):                # no common line: all changed
                for k in range(a_lo, a_hi):
                    changed_a[k] = True
                for k in range(b_lo, b_hi):
                    changed_b[k] = True
                continue
            x, y = split
            stack.append((x, a_hi, y, b_hi))
            stack.append((a_lo, x, b_lo, y))
        cost = changed_a.count(True) + changed_b.count(True)
        if cost > limit:
            raise Vault__Line_Diff__Too_Different(cost, limit)
        return changed_a, changed_b

    def middle_snake(self, a: list, a_lo: int, a_hi: int, b: list, b_lo: int, b_hi: int, limit: int):
        """A point (x, y) on a shortest edit path of a[a_lo:a_hi] → b[b_lo:b_hi], found by
        the forward and reverse searches meeting (Myers §4b). None when the two ranges
        share no line. Raises Vault__Line_Diff__Too_Different past `limit`."""
        n, m   = a_hi - a_lo, b_hi - b_lo
        max_d  = (n + m + 1) // 2
        offset = max_d
        size   = 2 * max_d + 2
        v1     = [-1] * size
        v2     = [-1] * size
        v1[offset + 1] = 0
        v2[offset + 1] = 0
        delta  = n - m
        front  = delta % 2 != 0
        k1_start = k1_end = k2_start = k2_end = 0
        for d in range(max_d):
            if 2 * d > limit:
                raise Vault__Line_Diff__Too_Different(2 * d, limit)
            for k1 in range(-d + k1_start, d + 1 - k1_end, 2):                          # forward search
                k1_offset = offset + k1
                if k1 == -d or (k1 != d and v1[k1_offset - 1] < v1[k1_offset + 1]):
                    x1 = v1[k1_offset + 1]
                else:
                    x1 = v1[k1_offset - 1] + 1
                y1 = x1 - k1
                while x1 < n and y1 < m and a[a_lo + x1] == b[b_lo + y1]:
                    x1 += 1
                    y1 += 1
                v1[k1_offset] = x1
                if x1 > n:
                    k1_end += 2
                elif y1 > m:
                    k1_start += 2
                elif front:
                    k2_offset = offset + delta - k1
                    if 0 <= k2_offset < size and v2[k2_offset] != -1 and x1 >= n - v2[k2_offset]:
                        return a_lo + x1, b_lo + y1
            for k2 in range(-d + k2_start, d + 1 - k2_end, 2):                          # reverse search
                k2_offset = offset + k2
                if k2 == -d or (k2 != d and v2[k2_offset - 1] < v2[k2_offset + 1]):
                    x2 = v2[k2_offset + 1]
                else:
                    x2 = v2[k2_offset - 1] + 1
                y2 = x2 - k2
                while x2 < n and y2 < m and a[a_hi - 1 - x2] == b[b_hi - 1 - y2]:
                    x2 += 1
                    y2 += 1
                v2[k2_offset] = x2
                if x2 > n:
                    k2_end += 2
                elif y2 > m:
                    k2_start += 2
                elif not front:
                    k1_offset = offset + delta - k2
                    if 0 <= k1_offset < size and v1[k1_offset] != -1:
                        x1 = v1[k1_offset]
                        y1 = offset + x1 - k1_offset
                        if x1 >= n - x2:
                            return a_lo + x1, b_lo + y1
        return None
