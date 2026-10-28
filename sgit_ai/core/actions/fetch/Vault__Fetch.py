import json
import os
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.network.api.Vault__API                    import Vault__API
from   sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.storage.Vault__Commit             import Vault__Commit
from   sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from   sgit_ai.storage.Vault__Storage               import Vault__Storage


class Vault__Fetch(Type_Safe):
    crypto      : Vault__Crypto
    api         : Vault__API
    storage     : Vault__Storage

    def fetch_commit_chain(self, obj_store: Vault__Object_Store, read_key: bytes,
                           from_commit_id: str, stop_at: str = None,
                           limit: int = 100) -> list[str]:
        """Walk the commit DAG backwards from from_commit_id, collecting new commit IDs.

        Uses BFS across ALL parents (not just first parent) so that merge
        commits on either side of the graph are correctly handled.

        Collects commits reachable from from_commit_id but NOT reachable from
        stop_at.  The stop_at commit itself is included (as the boundary
        marker) but its ancestors are excluded.

        Stops at root commits (no parents) or the limit.
        """
        pki = PKI__Crypto()
        vc  = Vault__Commit(crypto=self.crypto, pki=pki,
                            object_store=obj_store, ref_manager=Vault__Ref_Manager())

        def get_parents(cid):
            try:
                commit  = vc.load_commit(cid, read_key)
                parents = list(commit.parents) if commit.parents else []
                return [str(p) for p in parents if str(p)]
            except Exception:
                return []

        # Build the set of commits reachable from stop_at (these already
        # exist on the server and should not be uploaded again).
        stop_ancestors = set()
        if stop_at:
            queue = [stop_at]
            while queue and len(stop_ancestors) < limit:
                cid = queue.pop(0)
                if not cid or cid in stop_ancestors:
                    continue
                stop_ancestors.add(cid)
                queue.extend(get_parents(cid))

        # BFS from from_commit_id, collecting only new commits.
        chain   = []
        visited = set()
        queue   = [from_commit_id]

        while queue and len(chain) < limit:
            cid = queue.pop(0)
            if not cid or cid in visited:
                continue
            visited.add(cid)

            if cid in stop_ancestors:
                # Include stop_at itself as boundary marker, skip its ancestors
                if cid == stop_at:
                    chain.append(cid)
                continue

            chain.append(cid)
            queue.extend(get_parents(cid))

        return chain

    def find_lca(self, obj_store: Vault__Object_Store, read_key: bytes,
                 commit_a: str, commit_b: str, limit: int = 0) -> str:
        """The lowest common ancestor of two commits (Git's merge base), or None when
        the histories never meet. No cap on depth: the walk stops where they meet
        (Vault__Commit_Graph; the old 200-ancestor cap found no base on deeper
        histories, design__00 B6). `limit` is accepted and ignored."""
        from sgit_ai.storage.Vault__Commit_Graph import Vault__Commit_Graph
        return Vault__Commit_Graph(crypto=self.crypto, obj_store=obj_store).merge_base(commit_a, commit_b, read_key)
