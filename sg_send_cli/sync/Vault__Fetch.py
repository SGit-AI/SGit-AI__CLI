import json
import os
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.api.Vault__API                    import Vault__API
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sg_send_cli.objects.Vault__Commit             import Vault__Commit
from   sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage


class Vault__Fetch(Type_Safe):
    crypto      : Vault__Crypto
    api         : Vault__API
    storage     : Vault__Storage

    def fetch_commit_chain(self, obj_store: Vault__Object_Store, read_key: bytes,
                           from_commit_id: str, stop_at: str = None,
                           limit: int = 100) -> list[str]:
        """Walk the commit chain backwards from from_commit_id, collecting commit IDs.

        Stops when reaching stop_at, a root commit (no parents), or the limit.
        """
        pki    = PKI__Crypto()
        vc     = Vault__Commit(crypto=self.crypto, pki=pki,
                               object_store=obj_store, ref_manager=Vault__Ref_Manager())
        chain  = []
        current = from_commit_id

        while current and len(chain) < limit:
            if current == stop_at:
                chain.append(current)
                break
            chain.append(current)
            try:
                commit = vc.load_commit(current, read_key)
            except Exception:
                break

            parents = list(commit.parents) if commit.parents else []

            current = str(parents[0]) if parents else None

        return chain

    def find_lca(self, obj_store: Vault__Object_Store, read_key: bytes,
                 commit_a: str, commit_b: str, limit: int = 200) -> str:
        """Find the Lowest Common Ancestor of two commits.

        Uses a proper DAG LCA algorithm:
        1. Collect all ancestors of both commits
        2. Find common ancestors
        3. Filter to only the most recent (lowest) common ancestors by
           removing any that are proper ancestors of another common ancestor

        Returns None if no common ancestor found within the limit.
        """
        if commit_a == commit_b:
            return commit_a

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

        def collect_ancestors(start):
            result = set()
            queue  = [start] if start else []
            while queue and len(result) < limit:
                cid = queue.pop(0)
                if not cid or cid in result:
                    continue
                result.add(cid)
                queue.extend(get_parents(cid))
            return result

        ancestors_a = collect_ancestors(commit_a)
        ancestors_b = collect_ancestors(commit_b)

        common = ancestors_a & ancestors_b
        if not common:
            return None

        # Filter to LCA(s): remove any common ancestor that is a proper
        # ancestor of another common ancestor
        lca_set = set(common)
        for cid in common:
            cid_ancestors = collect_ancestors(cid)
            cid_ancestors.discard(cid)
            lca_set -= cid_ancestors

        return next(iter(lca_set)) if lca_set else None
