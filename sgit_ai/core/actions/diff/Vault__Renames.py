"""Vault__Renames — Git's rename detection (diffcore-rename.c, diffcore-delta.c), on flat
entries and, when given, their plaintext (design__04 §5.2).

Three passes, as Git runs them:
  1. exact     — same (content_hash, size); no limit. Several candidates: the one with the
                 same basename, else the first by path. Empty files are no exception (git
                 2.43 pairs e1 e2 -> f1 f2 in path order; the design's basename-only rule
                 was wrong, the oracle test pins it).
  2. basename  — a basename unique among the remaining sources and destinations, at the
                 raised threshold min + (100 - min) / 2; no limit (Git >= 2.33).
  3. inexact   — every source against every destination, skipped when sources x
                 destinations is over limit^2; the best four per destination, then the
                 highest scores first (same basename on ties), each path used once.

similarity() is Git's estimate_similarity: the file cut into spans (a span ends after
`\\n` or 64 bytes, `\\r` before `\\n` ignored in text), each span hashed with Git's own
32-bit accumulator hash, copied bytes counted per hash, score = copied * MAX_SCORE /
larger size. Content hashes are the committer's claim: good enough for display; a
merge must confirm exact pairs by bytes (verify_exact)."""
import posixpath
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from   sgit_ai.safe_types.Safe_UInt__Rename_Score      import Safe_UInt__Rename_Score
from   sgit_ai.schemas.diff.Schema__Rename_Pair        import Schema__Rename_Pair
from   sgit_ai.schemas.diff.Schema__Rename_Result      import Schema__Rename_Result

MAX_SCORE              = 60000
HASHBASE               = 107927
NUM_CANDIDATE_PER_DST  = 4
RENAME_MAX_BYTES       = 4 * 1024 * 1024
BINARY_PROBE_BYTES     = 8000
MASK32                 = 0xFFFFFFFF


class Vault__Renames(Type_Safe):
    min_score  : Safe_UInt__Rename_Score = 50
    limit      : Safe_UInt               = 1000
    enabled    : bool = True
    exact_only : bool = False
    span_memo  : object = None                                 # id(bytes) -> span counts, for one detect call

    def detect(self, deleted: dict, added: dict, content_of=None, verify_exact: bool = False) -> Schema__Rename_Result:
        """deleted / added: {path: flat entry}. content_of(entry) -> bytes | None. Without it
        only the exact pass runs. Never raises for a blob that cannot be read."""
        result = Schema__Rename_Result()
        if not self.enabled or not deleted or not added:
            return result
        self.span_memo = {}
        src, dst = dict(deleted), dict(added)
        self.exact_pass(src, dst, result, content_of if verify_exact else None)
        if content_of is None or self.exact_only or not src or not dst:
            return result
        contents = {}
        def content(side, path):
            key = (side, path)
            if key not in contents:
                entry = (src if side == 's' else dst).get(path)
                data  = None
                if entry is not None and int(entry.get('size') or 0) <= RENAME_MAX_BYTES:
                    try:
                        data = content_of(entry)
                    except Exception:                                    # unreadable: not a candidate
                        data = None
                if data is None:
                    result.unread += 1
                contents[key] = data
            return contents[key]
        self.basename_pass(src, dst, result, content)
        self.inexact_pass(src, dst, result, content)
        return result

    # --- pass 1 -------------------------------------------------------------------------

    def exact_pass(self, src: dict, dst: dict, result, verify) -> None:
        by_key = {}
        for path in sorted(src):
            key = self.exact_key(src[path])
            if key is not None:
                by_key.setdefault(key, []).append(path)
        for path in sorted(dst):
            key = self.exact_key(dst[path])
            candidates = [p for p in by_key.get(key, []) if p in src] if key is not None else []
            if not candidates:
                continue
            same   = [p for p in candidates if posixpath.basename(p) == posixpath.basename(path)]
            chosen = (same or candidates)[0]                             # empty files too (git 2.43: e1->f1, e2->f2)
            if verify is not None and verify(src[chosen]) != verify(dst[path]):
                continue                                                 # a claim the bytes do not confirm
            self.pair(result, src, dst, chosen, path, 100, exact=True)

    def exact_key(self, entry: dict):
        content_hash = entry.get('content_hash') or ''
        return (content_hash, int(entry.get('size') or 0)) if content_hash else None

    # --- pass 2 -------------------------------------------------------------------------

    def basename_pass(self, src: dict, dst: dict, result, content) -> None:
        threshold = self.score_units(int(self.min_score))
        threshold = threshold + (MAX_SCORE - threshold) // 2
        src_names, dst_names = self.unique_basenames(src), self.unique_basenames(dst)
        for name in sorted(set(src_names) & set(dst_names)):
            s, d = src_names[name], dst_names[name]
            a, b = content('s', s), content('d', d)
            if a is None or b is None:
                continue
            score = self.score(a, b, threshold)
            if score >= threshold:
                self.pair(result, src, dst, s, d, score * 100 // MAX_SCORE, exact=False)

    def unique_basenames(self, side: dict) -> dict:
        counts, paths = {}, {}
        for path in side:
            name = posixpath.basename(path)
            counts[name] = counts.get(name, 0) + 1
            paths[name]  = path
        return {name: paths[name] for name, n in counts.items() if n == 1}

    # --- pass 3 -------------------------------------------------------------------------

    def inexact_pass(self, src: dict, dst: dict, result, content) -> None:
        if not src or not dst:
            return
        limit = int(self.limit)
        if limit and (len(src) > limit or len(dst) > limit) and len(src) * len(dst) > limit * limit:
            result.limit_hit = True
            return
        result.candidates = len(src) * len(dst)
        minimum = self.score_units(int(self.min_score))
        kept    = []
        for d in sorted(dst):
            b = content('d', d)
            if b is None:
                continue
            scored = []
            for s in sorted(src):
                a = content('s', s)
                if a is None:
                    continue
                score = self.score(a, b, minimum)
                if score >= minimum:
                    scored.append((score, int(posixpath.basename(s) == posixpath.basename(d)), s, d))
            scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
            kept += scored[:NUM_CANDIDATE_PER_DST]
        kept.sort(key=lambda t: (-t[0], -t[1], t[3], t[2]))
        for score, _, s, d in kept:
            if s in src and d in dst:
                self.pair(result, src, dst, s, d, score * 100 // MAX_SCORE, exact=False)

    # --- scoring ------------------------------------------------------------------------

    def percent_from_option(self, text: str) -> int:
        """`-M<n>` as Git's parse_rename_score reads it: digits are a fraction (`9` and `90`
        are 90%, `5` is 50%), a `%` makes them a percentage, `0.9` is 90%."""
        num, scale, dot = 0, 1, False
        for ch in str(text or ''):
            if ch == '.' and not dot:
                scale, dot = 1, True
            elif ch == '%':
                scale = scale * 100 if dot else 100
                break
            elif ch.isdigit():
                if scale < 100000:
                    scale *= 10
                    num    = num * 10 + int(ch)
            else:
                break
        if not str(text or '').strip():
            return 50
        return 100 if num >= scale else MAX_SCORE * num // scale * 100 // MAX_SCORE

    def score_units(self, percent: int) -> int:
        return percent * MAX_SCORE // 100

    def similarity(self, src: bytes, dst: bytes) -> int:
        """Percent, as Git prints it."""
        return self.score(src, dst, 0) * 100 // MAX_SCORE

    def score(self, src: bytes, dst: bytes, minimum: int) -> int:
        """Git's estimate_similarity, in MAX_SCORE units (0 below the size precheck)."""
        max_size, base_size = max(len(src), len(dst)), min(len(src), len(dst))
        if not max_size or not len(dst) or not len(src):
            return 0
        if max_size * (MAX_SCORE - minimum) < (max_size - base_size) * MAX_SCORE:
            return 0
        spans_src, spans_dst = self.spans(src), self.spans(dst)
        copied = sum(min(count, spans_dst[h]) for h, count in spans_src.items() if h in spans_dst)
        return copied * MAX_SCORE // max_size

    def spans(self, data: bytes) -> dict:
        """{span hash: bytes} as diffcore-delta.c's hash_chars."""
        memo_key = id(data)
        if self.span_memo is not None and memo_key in self.span_memo:
            return self.span_memo[memo_key][1]
        is_text = b'\x00' not in data[:BINARY_PROBE_BYTES]
        counts, accum1, accum2, n, size, i = {}, 0, 0, 0, len(data), 0
        while i < size:
            c  = data[i]
            i += 1
            if is_text and c == 0x0d and i < size and data[i] == 0x0a:
                continue
            old_1  = accum1
            accum1 = ((accum1 << 7) ^ (accum2 >> 25)) & MASK32
            accum2 = ((accum2 << 7) ^ (old_1 >> 25)) & MASK32
            accum1 = (accum1 + c) & MASK32
            n += 1
            if n < 64 and c != 0x0a:
                continue
            h = (accum1 + accum2 * 0x61) % HASHBASE
            counts[h] = counts.get(h, 0) + n
            n, accum1, accum2 = 0, 0, 0
        if n > 0:
            h = (accum1 + accum2 * 0x61) % HASHBASE
            counts[h] = counts.get(h, 0) + n
        if self.span_memo is not None:
            self.span_memo[memo_key] = (data, counts)                     # data kept so its id stays unique
        return counts

    def pair(self, result, src: dict, dst: dict, old: str, new: str, score: int, exact: bool) -> None:
        result.pairs.append(Schema__Rename_Pair(old_path=old, new_path=new, score=score, exact=exact))
        src.pop(old)
        dst.pop(new)
