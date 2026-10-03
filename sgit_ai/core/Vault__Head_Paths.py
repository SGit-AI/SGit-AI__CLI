"""Vault__Head_Paths — the working branch head's path set, best-effort.

Feeds the tracked-wins rule in Vault__Ignore (decision 17): every walk that
scans a vault work tree needs to know which paths the head already tracks, so
a newly-added ignore rule cannot silently record them as deletions. Resolves
the working branch exactly the way status/commit do (Vault__Sync__Base helpers),
so the tracked set always matches the tree those commands diff against.
"""
from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.storage.Vault__Commit    import Vault__Commit
from sgit_ai.storage.Vault__Sub_Tree  import Vault__Sub_Tree
from sgit_ai.core.Vault__Sync__Base   import Vault__Sync__Base


class Vault__Head_Paths(Vault__Sync__Base):

    def paths(self, directory: str) -> set:
        """Rel paths in the working branch's head tree; empty set on any failure.

        Never raises: a directory that is not a vault, a missing key, or an
        empty history all mean "no tracked paths", which callers treat as
        plain ignore-rule matching.

        Fail-open safety (review A6): returning an empty set here disables
        tracked-wins, which would re-expose the P0 deletion hazard IF a scan
        could still succeed against the same corrupt state. It cannot: every
        scan site derives its head tree the same way this does
        (_init_components → load_branch_index → read_ref → load_commit →
        flatten), so a corruption that empties this set also makes the scan
        (status/commit) raise loudly rather than silently rebuild an empty
        tree. The two fail together — pinned by
        test_A6__head_unreadable_makes_scan_fail_loud. Do not make the scan
        path tolerant of a corrupt head without also gating tracked-wins on
        an explicit "head is empty" signal.
        """
        try:
            if self.crypto is None:
                self.crypto = Vault__Crypto()
            c            = self._init_components(directory)
            config       = self._read_local_config(directory, c.storage)
            index_id     = c.branch_index_file_id
            if not index_id:
                return set()
            branch_index = c.branch_manager.load_branch_index(directory, index_id, c.read_key)
            branch_meta  = self._resolve_working_branch(config, branch_index, c.branch_manager,
                                                        self._tracked_branch_name(directory))
            if not branch_meta:
                return set()
            head = c.ref_manager.read_ref(str(branch_meta.head_ref_id), c.read_key)
            if not head:
                return set()
            vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                         object_store=c.obj_store, ref_manager=c.ref_manager)
            commit       = vault_commit.load_commit(head, c.read_key)
            sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
            return set(sub_tree.flatten(str(commit.tree_id), c.read_key).keys())
        except Exception:
            return set()
