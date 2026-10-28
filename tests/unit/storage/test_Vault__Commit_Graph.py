"""Merge bases and reachability with no commit cap (phase 0: design__00 F2/B6).

find_lca collected at most 200 ancestors per side: on a deeper history it found no
base, so a pull merged against an empty base and a push more than 200 commits ahead
was rejected as diverged. The graph is checked against brute force (full ancestor
sets) on random histories, and on a fork deeper than the old cap."""
import os
import random
import shutil
import tempfile

import pytest

from sgit_ai.core.actions.fetch.Vault__Fetch     import Vault__Fetch
from sgit_ai.crypto.PKI__Crypto                  import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path
from sgit_ai.storage.Vault__Commit               import Vault__Commit
from sgit_ai.storage.Vault__Commit_Graph         import Vault__Commit_Graph
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager          import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Sub_Tree             import Vault__Sub_Tree

READ_KEY = bytes(range(32))


class Test_Vault__Commit_Graph:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.crypto = Vault__Crypto()
        sg_dir      = os.path.join(self.tmp, '.sg_vault')
        self.store  = Vault__Object_Store(vault_path=Safe_Str__Vault_Path(sg_dir), crypto=self.crypto)
        self.vc     = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=self.store,
                                    ref_manager=Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto))
        self.tree   = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.store).build_from_flat({}, READ_KEY)
        self.clock  = 1_700_000_000_000

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def commit(self, *parents) -> str:
        self.clock += 1000
        return self.vc.create_commit(read_key=READ_KEY, tree_id=self.tree, parent_ids=list(parents),
                                     message=str(self.clock), timestamp_ms=self.clock)

    def chain(self, start: str, n: int) -> list:
        ids = []
        for _ in range(n):
            start = self.commit(*([start] if start else []))
            ids.append(start)
        return ids

    def graph(self) -> Vault__Commit_Graph:
        return Vault__Commit_Graph(crypto=self.crypto, obj_store=self.store)

    def ancestors(self, cid, parents) -> set:
        seen, stack = set(), [cid]
        while stack:
            c = stack.pop()
            if c not in seen:
                seen.add(c)
                stack.extend(parents[c])
        return seen

    def test_a_fork_deeper_than_the_old_cap(self):
        trunk = self.chain(None, 20)
        ours  = self.chain(trunk[-1], 250)
        their = self.chain(trunk[-1], 250)
        graph = self.graph()
        assert graph.merge_base(ours[-1], their[-1], READ_KEY) == trunk[-1]
        assert graph.count_unique(ours[-1], their[-1], READ_KEY) == 250
        assert graph.count_unique(their[-1], ours[-1], READ_KEY) == 250
        fetcher = Vault__Fetch(crypto=self.crypto, api=None, storage=Vault__Storage())
        assert fetcher.find_lca(self.store, READ_KEY, ours[-1], their[-1]) == trunk[-1]   # was None

    def test_a_push_far_ahead_is_a_fast_forward(self):
        trunk = self.chain(None, 5)
        ahead = self.chain(trunk[-1], 300)
        graph = self.graph()
        assert graph.merge_base(ahead[-1], trunk[-1], READ_KEY) == trunk[-1]
        assert graph.is_ancestor(trunk[-1], ahead[-1], READ_KEY)
        assert not graph.is_ancestor(ahead[-1], trunk[-1], READ_KEY)

    def test_the_walk_stops_where_the_histories_meet(self):
        trunk = self.chain(None, 400)
        a, b  = self.commit(trunk[-1]), self.commit(trunk[-1])
        graph = self.graph()
        assert graph.merge_base(a, b, READ_KEY) == trunk[-1]
        assert len(graph.memo) < 10                                       # 400 commits of history never loaded

    def test_trivial_cases(self):
        c1, c2 = self.chain(None, 2)
        other  = self.commit()
        graph  = self.graph()
        assert graph.merge_base(c1, c1, READ_KEY) == c1
        assert graph.merge_base(c1, c2, READ_KEY) == c1
        assert graph.merge_base(c2, other, READ_KEY) is None
        assert graph.count_unique(c2, c2, READ_KEY) == 0
        assert graph.count_unique(c2, '', READ_KEY)  == 2
        assert graph.count_unique('', c2, READ_KEY)  == 0

    def test_criss_cross_has_two_bases_and_one_is_chosen_deterministically(self):
        base = self.commit()
        x, y = self.commit(base), self.commit(base)
        m1   = self.commit(x, y)
        m2   = self.commit(y, x)
        graph = self.graph()
        assert sorted(graph.merge_bases(m1, m2, READ_KEY)) == sorted([x, y])
        assert graph.merge_base(m1, m2, READ_KEY) == graph.merge_base(m2, m1, READ_KEY)

    @pytest.mark.parametrize('seed', range(25))
    def test_random_histories_match_brute_force(self, seed):
        rng     = random.Random(seed)
        parents = {}
        nodes   = []
        for i in range(rng.randrange(5, 60)):
            k  = 0 if not nodes else (1 if rng.random() < 0.8 or len(nodes) < 2 else 2)
            ps = rng.sample(nodes[-15:], min(k, len(nodes[-15:]))) if nodes else []
            cid = self.commit(*ps)
            parents[cid] = ps
            nodes.append(cid)
        graph = self.graph()
        for _ in range(10):
            a, b    = rng.choice(nodes), rng.choice(nodes)
            anc_a   = self.ancestors(a, parents)
            anc_b   = self.ancestors(b, parents)
            common  = anc_a & anc_b
            best    = {c for c in common if not any(c in self.ancestors(o, parents) - {o} for o in common)}
            assert set(graph.merge_bases(a, b, READ_KEY)) == best
            assert graph.count_unique(a, b, READ_KEY) == len(anc_a - anc_b)
            assert graph.is_ancestor(a, b, READ_KEY) == (a in anc_b)
