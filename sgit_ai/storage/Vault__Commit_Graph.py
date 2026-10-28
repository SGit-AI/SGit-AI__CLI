"""Vault__Commit_Graph — merge bases and reachability with no commit cap (design__00 F2).

`find_lca` and `_walk_commit_ids` collected at most 200 ancestors per side, so on a
history deeper than that a merge found no base (every file both sides touched became
a conflict), a push more than 200 commits ahead was rejected as diverged, and
ahead/behind counts were cut short (design__00 B6).

This is Git's paint_down_to_common: walk both sides at once, newest commit first,
painting each commit with the side(s) it is reachable from. A commit reached from
both is a common ancestor; what lies below it is stale, and the walk stops as soon
as only stale commits are queued. The cost follows the distance to the merge base,
not the length of the history. Commits are ordered by timestamp, as Git orders them
without a commit-graph file: a clock skewed far enough can make the answer a common
ancestor that is not the lowest, never one that is not common.

Parents are memoised per instance, so bisect (design__05) and rebase (design__07)
can ask many questions of one graph. A commit missing from the local store reads
as a root.
"""
import heapq
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.PKI__Crypto                   import PKI__Crypto
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.storage.Vault__Object_Store          import Vault__Object_Store

SIDE_A = 1
SIDE_B = 2
STALE  = 4
RESULT = 8
BOTH   = SIDE_A | SIDE_B


class Vault__Commit_Graph(Type_Safe):
    crypto    : Vault__Crypto
    obj_store : Vault__Object_Store
    memo      : object = None                          # commit id -> (timestamp_ms, [parent ids])

    def info(self, commit_id: str, read_key: bytes) -> tuple:
        """(timestamp_ms, [parent ids]) of a commit; (0, []) when it is not in the store."""
        if self.memo is None:
            self.memo = {}
        found = self.memo.get(commit_id)
        if found is None:
            found = (0, [])
            try:
                from sgit_ai.storage.Vault__Commit      import Vault__Commit
                from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager
                commit = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=self.obj_store,
                                       ref_manager=Vault__Ref_Manager()).load_commit(commit_id, read_key)
                found  = (int(commit.timestamp_ms or 0), [str(p) for p in (commit.parents or []) if str(p)])
            except Exception:
                pass
            self.memo[commit_id] = found
        return found

    def parents(self, commit_id: str, read_key: bytes) -> list:
        return self.info(commit_id, read_key)[1]

    def merge_bases(self, commit_a: str, commit_b: str, read_key: bytes) -> list:
        """The best common ancestors of a and b (none an ancestor of another), newest
        first. [] when the two histories never meet."""
        if not commit_a or not commit_b:
            return []
        if commit_a == commit_b:
            return [commit_a]
        flags, results, _ = self.paint_down({commit_a: SIDE_A, commit_b: SIDE_B}, read_key, find_bases=True)
        bases = [cid for cid in results if not flags[cid] & STALE]       # a result reached from a better one is not
        return self.remove_redundant(bases, read_key)

    def merge_base(self, commit_a: str, commit_b: str, read_key: bytes) -> str:
        """One best common ancestor (the newest, then the smallest id), or None."""
        bases = self.merge_bases(commit_a, commit_b, read_key)
        return bases[0] if bases else None

    def is_ancestor(self, ancestor: str, descendant: str, read_key: bytes) -> bool:
        """True when `ancestor` is `descendant` or reachable from it."""
        if not ancestor or not descendant:
            return False
        return ancestor in self.merge_bases(ancestor, descendant, read_key)

    def count_unique(self, from_head: str, stop_head: str, read_key: bytes) -> int:
        """How many commits are reachable from from_head and not from stop_head (git
        rev-list --count stop..from). The walk stops where the two histories meet."""
        if not from_head or from_head == stop_head:
            return 0
        if not stop_head:
            return len(self.reachable(from_head, read_key))
        flags, _, popped = self.paint_down({from_head: SIDE_A, stop_head: SIDE_B}, read_key, find_bases=False)
        return sum(1 for cid in popped if flags[cid] & BOTH == SIDE_A)

    def reachable(self, start: str, read_key: bytes, stop: set = None) -> set:
        """Every commit reachable from start (inclusive), not entering `stop`."""
        stop    = stop or set()
        visited = set()
        pending = [start] if start else []
        while pending:
            cid = pending.pop()
            if cid in visited or cid in stop:
                continue
            visited.add(cid)
            pending.extend(self.parents(cid, read_key))
        return visited

    def paint_down(self, seeds: dict, read_key: bytes, find_bases: bool) -> tuple:
        """Walk from the seeds, newest first, painting parents with their children's
        sides, until every queued commit is stale. find_bases: a commit painted with
        both sides is a result and its ancestors are stale (merge bases). Otherwise a
        commit painted with both sides is the stale one (counting). Returns (flags,
        results, popped). `active` counts queued entries that are not stale, so the
        stop test costs nothing per step (Git scans the queue)."""
        flags   = dict(seeds)
        queue   = []
        queued  = {}
        results = []
        popped  = set()
        state   = dict(active=0, counter=0)

        def stale(f):
            return bool(f & STALE) if find_bases else f & BOTH == BOTH

        def push(cid):
            state['counter'] += 1
            heapq.heappush(queue, (-self.info(cid, read_key)[0], state['counter'], cid))
            queued[cid] = queued.get(cid, 0) + 1
            if not stale(flags[cid]):
                state['active'] += 1

        def add(cid, f) -> bool:
            old = flags.get(cid, 0)
            new = old | f
            if new == old:
                return False
            flags[cid] = new
            if queued.get(cid) and not stale(old) and stale(new):
                state['active'] -= queued[cid]
            return True

        for cid in seeds:
            push(cid)
        while state['active'] > 0:
            _, _, cid = heapq.heappop(queue)
            queued[cid] -= 1
            if not stale(flags[cid]):
                state['active'] -= 1
            popped.add(cid)
            here = flags[cid] & (BOTH | STALE)
            if find_bases and here & BOTH == BOTH:
                if not flags[cid] & RESULT:
                    flags[cid] |= RESULT
                    results.append(cid)
                here |= STALE
            for parent in self.parents(cid, read_key):
                if add(parent, here):
                    push(parent)
        return flags, results, popped

    def remove_redundant(self, bases: list, read_key: bytes) -> list:
        """Drop any base that is an ancestor of another (Git's remove_redundant: only
        criss-cross histories have more than one), then order newest first, the
        smallest id breaking a tie."""
        if len(bases) > 1:
            keep = [cid for cid in bases
                    if not any(other != cid and cid in self.reachable(other, read_key) for other in bases)]
            bases = keep or bases
        return sorted(bases, key=lambda cid: (-self.info(cid, read_key)[0], cid))
