import json
import os
from   collections                               import deque
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.network.api.Vault__API                    import Vault__API
from   sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.storage.Vault__Commit_Graph       import Vault__Commit_Graph
from   sgit_ai.storage.Vault__Storage               import Vault__Storage


class Vault__Fetch(Type_Safe):
    crypto      : Vault__Crypto
    api         : Vault__API
    storage     : Vault__Storage

    def fetch_commit_chain(self, obj_store: Vault__Object_Store, read_key: bytes,
                           from_commit_id: str, stop_at: str = None,
                           limit: int = 0) -> list[str]:
        """Every commit reachable from from_commit_id and not from stop_at (git rev-list
        stop_at..from_commit_id), newest first in breadth-first order across all parents,
        then stop_at itself as the boundary marker when the walk reaches it.

        No cap: push uploads exactly this list. It used to stop at 100 commits (and at 100
        known ancestors of stop_at), so a push of 101 or more uploaded only the newest 100
        and moved the ref over a gap no later push filled (cli.build BR-1). `limit` > 0
        keeps the first `limit` entries."""
        if not from_commit_id:
            return []
        graph = Vault__Commit_Graph(crypto=self.crypto, obj_store=obj_store)
        new   = graph.unique(from_commit_id, stop_at, read_key) if stop_at else graph.reachable(from_commit_id, read_key)
        chain, visited, queue = [], set(), deque([from_commit_id])
        while queue:
            cid = queue.popleft()
            if not cid or cid in visited:
                continue
            visited.add(cid)
            if cid not in new:
                if cid == stop_at:
                    chain.append(cid)
                continue
            chain.append(cid)
            queue.extend(graph.parents(cid, read_key))
        return chain[:limit] if limit else chain

    def missing_parents(self, chain: list, stop_at: str, obj_store: Vault__Object_Store, read_key: bytes) -> list:
        """The parents of the chain's commits that are neither in the chain nor reachable
        from stop_at (so neither uploaded by this push nor already on the host). Push
        refuses before uploading anything when this is not empty."""
        graph   = Vault__Commit_Graph(crypto=self.crypto, obj_store=obj_store)
        members = set(chain)
        missing = []
        for cid in chain:
            if cid == stop_at:
                continue
            for parent in graph.parents(cid, read_key):
                if parent in members or parent == stop_at or parent in missing:
                    continue
                if not (stop_at and graph.is_ancestor(parent, stop_at, read_key)):
                    missing.append(parent)
        return missing

    def find_lca(self, obj_store: Vault__Object_Store, read_key: bytes,
                 commit_a: str, commit_b: str, limit: int = 0) -> str:
        """The lowest common ancestor of two commits (Git's merge base), or None when
        the histories never meet. No cap on depth: the walk stops where they meet
        (Vault__Commit_Graph; the old 200-ancestor cap found no base on deeper
        histories, design__00 B6). `limit` is accepted and ignored."""
        from sgit_ai.storage.Vault__Commit_Graph import Vault__Commit_Graph
        return Vault__Commit_Graph(crypto=self.crypto, obj_store=obj_store).merge_base(commit_a, commit_b, read_key)
