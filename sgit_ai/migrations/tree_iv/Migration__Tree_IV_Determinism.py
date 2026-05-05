"""Migration__Tree_IV_Determinism — re-encrypt tree objects with deterministic HMAC-IV.

Old vaults (pre-May-1) used random IV for tree objects, preventing CAS dedup.
This migration re-encrypts all tree objects with HMAC-derived IV, then rewrites
commits and refs to reference the new tree IDs.
"""
import json
import os

from sgit_ai.migrations.Migration         import Migration
from sgit_ai.safe_types.Safe_Str__Migration_Name import Safe_Str__Migration_Name


class Migration__Tree_IV_Determinism(Migration):
    name = Safe_Str__Migration_Name('tree-iv-determinism')

    def is_applied(self, sg_dir: str, read_key: bytes) -> bool:
        """Return True if no tree objects need re-encryption."""
        from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Commit       import Vault__Commit

        crypto    = Vault__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        vc        = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                                  object_store=obj_store, ref_manager=ref_mgr)

        tree_ids = self._collect_tree_ids(ref_mgr, vc, obj_store, read_key)
        if not tree_ids:
            return True  # no trees → nothing to do

        # Sample first 5 trees — if a vault has N trees with only 3 random-IV
        # outliers, sampling may miss them and falsely report "applied".  The
        # cost is suboptimal dedup, not corruption; the full apply() is safe to
        # run again if in doubt.
        for tid in list(tree_ids)[:5]:
            try:
                old_cipher = obj_store.load(tid)
                plaintext  = crypto.decrypt(read_key, old_cipher)
                new_cipher = crypto.encrypt_deterministic(read_key, plaintext)
                new_tid    = obj_store._compute_id(new_cipher)
                if new_tid != tid:
                    return False  # found a non-deterministic tree
            except (FileNotFoundError, OSError):
                pass  # object not present locally — skip sample
            except Exception as e:
                raise RuntimeError(
                    f'tree-iv-determinism: decrypt failure while checking tree {tid!r}: {e}'
                ) from e
        return True

    def apply(self, sg_dir: str, read_key: bytes) -> dict:
        """Re-encrypt tree objects, rewrite commits, update refs."""
        from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Commit       import Vault__Commit

        crypto    = Vault__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
        ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
        vc        = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                                  object_store=obj_store, ref_manager=ref_mgr)

        # ── 1. Collect all commit IDs and tree IDs ───────────────────────────
        head_commit_ids, commit_parent_map, commit_tree_map, tree_children, all_tree_ids = \
            self._collect_commit_and_tree_graph(ref_mgr, vc, obj_store, read_key)

        if not all_tree_ids:
            return {'n_trees': 0, 'n_commits': 0, 'n_refs': 0}

        # ── 2. Topological sort of trees (leaves first) ──────────────────────
        sorted_trees = self._topo_sort_trees(all_tree_ids, tree_children)

        # ── 3. Re-encrypt trees bottom-up, build tree_mapping ───────────────
        tree_mapping = self._reencrypt_trees(sorted_trees, obj_store, crypto, read_key)

        if not tree_mapping:
            return {'n_trees': 0, 'n_commits': 0, 'n_refs': 0}

        # ── 4. Save backup of old tree IDs ───────────────────────────────────
        backup_path = os.path.join(sg_dir, 'local', 'pre-migration-trees.json')
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with open(backup_path, 'w') as f:
            json.dump({'migrated_trees': sorted(tree_mapping.keys())}, f, indent=2)

        # ── 5. Topological sort of commits (oldest first) ────────────────────
        sorted_commits = self._topo_sort_commits(head_commit_ids, commit_parent_map)

        # ── 6. Rewrite commits ───────────────────────────────────────────────
        commit_mapping = self._rewrite_commits(
            sorted_commits, commit_tree_map, commit_parent_map, tree_mapping, vc, read_key
        )

        # ── 7. Update refs ────────────────────────────────────────────────────
        n_refs = self._update_refs(ref_mgr, commit_mapping, read_key)

        # ── 8. Delete old tree objects ───────────────────────────────────────
        for old_tid in tree_mapping:
            path = obj_store.object_path(old_tid)
            try:
                os.remove(path)
            except OSError:
                pass

        return {'n_trees': len(tree_mapping), 'n_commits': len(commit_mapping), 'n_refs': n_refs}

    # ── helpers ────────────────────────────────────────────────────────────────

    def _collect_tree_ids(self, ref_mgr, vc, obj_store, read_key) -> set:
        """Return the set of all reachable tree IDs (from all refs)."""
        head_ids = [ref_mgr.read_ref(r, read_key)
                    for r in ref_mgr.list_refs()]
        head_ids = [h for h in head_ids if h]
        if not head_ids:
            return set()

        visited_c, tree_ids = set(), set()
        corrupt_commits     = []
        queue = list(head_ids)
        while queue:
            cid = queue.pop(0)
            if cid in visited_c:
                continue
            visited_c.add(cid)
            try:
                commit = vc.load_commit(cid, read_key)
                if commit.tree_id:
                    tree_ids.add(str(commit.tree_id))
                for p in (commit.parents or []):
                    queue.append(str(p))
            except Exception as e:
                corrupt_commits.append({'id': cid, 'error': str(e)})

        if corrupt_commits:
            examples = ', '.join(c['id'] for c in corrupt_commits[:3])
            raise RuntimeError(
                f'tree-iv-determinism: {len(corrupt_commits)} commit(s) failed to decrypt '
                f'(vault may be corrupt): {examples}'
            )

        corrupt_trees = []
        visited_t, tqueue = set(), list(tree_ids)
        while tqueue:
            tid = tqueue.pop(0)
            if not tid or tid in visited_t:
                continue
            visited_t.add(tid)
            try:
                tree = vc.load_tree(tid, read_key)
                for entry in tree.entries:
                    sub = str(entry.tree_id) if entry.tree_id else None
                    if sub:
                        tree_ids.add(sub)
                        tqueue.append(sub)
            except (FileNotFoundError, OSError):
                pass  # object not present locally — skip (sparse clone, or deleted old ref)
            except Exception as e:
                corrupt_trees.append({'id': tid, 'error': str(e)})

        if corrupt_trees:
            examples = ', '.join(t['id'] for t in corrupt_trees[:3])
            raise RuntimeError(
                f'tree-iv-determinism: {len(corrupt_trees)} tree(s) failed to decrypt '
                f'(vault may be corrupt): {examples}'
            )
        return tree_ids

    def _collect_commit_and_tree_graph(self, ref_mgr, vc, obj_store, read_key):
        head_commit_ids, commit_parent_map, commit_tree_map = [], {}, {}
        tree_children, all_tree_ids = {}, set()

        for ref_id in ref_mgr.list_refs():
            cid = ref_mgr.read_ref(ref_id, read_key)
            if cid:
                head_commit_ids.append(cid)

        corrupt_commits = []
        visited_c = set()
        queue = list(head_commit_ids)
        while queue:
            cid = queue.pop(0)
            if cid in visited_c:
                continue
            visited_c.add(cid)
            try:
                commit = vc.load_commit(cid, read_key)
                parents = [str(p) for p in (commit.parents or [])]
                commit_parent_map[cid] = parents
                commit_tree_map[cid]   = str(commit.tree_id) if commit.tree_id else ''
                queue.extend(parents)
            except Exception as e:
                corrupt_commits.append({'id': cid, 'error': str(e)})
                commit_parent_map[cid] = []
                commit_tree_map[cid]   = ''

        if corrupt_commits:
            examples = ', '.join(c['id'] for c in corrupt_commits[:3])
            raise RuntimeError(
                f'tree-iv-determinism: {len(corrupt_commits)} commit(s) failed to decrypt '
                f'(vault may be corrupt): {examples}'
            )

        corrupt_trees = []
        visited_t = set()
        tqueue = [commit_tree_map[c] for c in visited_c if commit_tree_map.get(c)]
        tqueue = list(set(tqueue))
        while tqueue:
            tid = tqueue.pop(0)
            if not tid or tid in visited_t:
                continue
            visited_t.add(tid)
            all_tree_ids.add(tid)
            try:
                tree = vc.load_tree(tid, read_key)
                subs = []
                for entry in tree.entries:
                    sub = str(entry.tree_id) if entry.tree_id else None
                    if sub:
                        subs.append(sub)
                        all_tree_ids.add(sub)
                        tqueue.append(sub)
                tree_children[tid] = subs
            except (FileNotFoundError, OSError):
                tree_children[tid] = []  # object not present locally — skip
            except Exception as e:
                corrupt_trees.append({'id': tid, 'error': str(e)})
                tree_children[tid] = []

        if corrupt_trees:
            examples = ', '.join(t['id'] for t in corrupt_trees[:3])
            raise RuntimeError(
                f'tree-iv-determinism: {len(corrupt_trees)} tree(s) failed to decrypt '
                f'(vault may be corrupt): {examples}'
            )

        return head_commit_ids, commit_parent_map, commit_tree_map, tree_children, all_tree_ids

    def _topo_sort_trees(self, all_tree_ids: set, tree_children: dict) -> list:
        """Return trees in topological order: leaves first, roots last."""
        parents_of = {}
        for parent, children in tree_children.items():
            for child in children:
                parents_of.setdefault(child, set()).add(parent)

        in_deg = {tid: len(set(tree_children.get(tid, []))) for tid in all_tree_ids}
        queue  = [tid for tid, d in in_deg.items() if d == 0]
        result = []
        while queue:
            tid = queue.pop(0)
            result.append(tid)
            for parent in parents_of.get(tid, set()):
                in_deg[parent] -= 1
                if in_deg[parent] == 0:
                    queue.append(parent)
        unsorted = [tid for tid in all_tree_ids if tid not in set(result)]
        if unsorted:
            raise RuntimeError(
                f'Vault tree graph contains a cycle or unreachable nodes: '
                f'{unsorted[:3]}... ({len(unsorted)} total). '
                f'Migration aborted to prevent silent corruption.'
            )
        return result

    def _reencrypt_trees(self, sorted_trees, obj_store, crypto, read_key) -> dict:
        """Re-encrypt trees bottom-up. Returns old_id → new_id mapping."""
        tree_mapping = {}
        for old_tid in sorted_trees:
            try:
                old_cipher = obj_store.load(old_tid)
                plaintext  = crypto.decrypt(read_key, old_cipher)

                tree_data = json.loads(plaintext)
                for entry in tree_data.get('entries', []):
                    sub = entry.get('tree_id')
                    if sub and sub in tree_mapping:
                        entry['tree_id'] = tree_mapping[sub]

                updated_plaintext = json.dumps(tree_data).encode()
                new_cipher        = crypto.encrypt_deterministic(read_key, updated_plaintext)
                new_tid           = obj_store._compute_id(new_cipher)

                if new_tid != old_tid:
                    obj_store.store(new_cipher)
                    tree_mapping[old_tid] = new_tid
            except (FileNotFoundError, OSError):
                pass  # object not present locally — nothing to re-encrypt, skip
            except Exception as e:
                raise RuntimeError(
                    f'tree-iv-determinism: failed to re-encrypt tree {old_tid!r}: {e}. '
                    f'Migration aborted — vault data is unchanged.'
                ) from e
        return tree_mapping

    def _topo_sort_commits(self, head_commit_ids, commit_parent_map) -> list:
        """Return commits in topological order: oldest (root) first."""
        children_of = {}
        all_cids    = set(commit_parent_map.keys())
        in_deg      = {cid: 0 for cid in all_cids}
        for cid, parents in commit_parent_map.items():
            for p in parents:
                in_deg[cid] += 1
                children_of.setdefault(p, []).append(cid)

        queue  = [cid for cid, d in in_deg.items() if d == 0]
        result = []
        while queue:
            cid = queue.pop(0)
            result.append(cid)
            for child in children_of.get(cid, []):
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    queue.append(child)
        unsorted = [cid for cid in all_cids if cid not in set(result)]
        if unsorted:
            raise RuntimeError(
                f'Vault commit graph contains a cycle or unreachable nodes: '
                f'{unsorted[:3]}... ({len(unsorted)} total). '
                f'Migration aborted to prevent silent corruption.'
            )
        return result

    def _rewrite_commits(self, sorted_commits, commit_tree_map, commit_parent_map,
                         tree_mapping, vc, read_key) -> dict:
        """Rewrite commits that reference migrated trees. Returns old_id → new_id."""
        commit_mapping = {}
        for old_cid in sorted_commits:
            old_tree_id = commit_tree_map.get(old_cid, '')
            new_tree_id = tree_mapping.get(old_tree_id, old_tree_id)
            old_parents = commit_parent_map.get(old_cid, [])
            new_parents = [commit_mapping.get(p, p) for p in old_parents]

            if new_tree_id == old_tree_id and new_parents == old_parents:
                continue

            try:
                commit  = vc.load_commit(old_cid, read_key)
                new_cid = vc.create_commit(
                    read_key     = read_key,
                    tree_id      = new_tree_id,
                    parent_ids   = new_parents,
                    message_enc  = str(commit.message_enc) if commit.message_enc else None,
                    branch_id    = str(commit.branch_id) if commit.branch_id else None,
                    timestamp_ms = int(str(commit.timestamp_ms)) if commit.timestamp_ms else None,
                )
                commit_mapping[old_cid] = new_cid
            except Exception as e:
                raise RuntimeError(
                    f'tree-iv-determinism: failed to rewrite commit {old_cid!r}: {e}. '
                    f'Migration aborted — refs not yet updated, vault is recoverable.'
                ) from e
        return commit_mapping

    def _update_refs(self, ref_mgr, commit_mapping, read_key) -> int:
        # Branch-index entries reference ref-file IDs, not commit IDs — no branch-index update needed.
        n = 0
        for ref_id in ref_mgr.list_refs():
            old_cid = ref_mgr.read_ref(ref_id, read_key)
            if old_cid and old_cid in commit_mapping:
                ref_mgr.write_ref(ref_id, commit_mapping[old_cid], read_key)
                n += 1
        return n
