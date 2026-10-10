"""Vault__Incoming_Check — the signature policy for a head about to be accepted.

The one rule (review d3b8eef N2/N3): nothing writes a local named ref or a baseline
except verify-then-accept. Pull (writable and read-only) and branch switch call this
before they write; status never writes.
"""
import os
from sgit_ai.core.Vault__Sync__Base import Vault__Sync__Base


class Vault__Incoming_Check(Vault__Sync__Base):

    def require_signatures(self, directory: str, c, read_key: bytes, incoming_head: str, held_head: str) -> None:
        """With feature 'signatures-required' on the vault, every commit from `incoming_head`
        down to what this clone already holds (everything reachable from `held_head`) must
        verify; the first that does not raises Vault__Signature_Error by name. Commits from
        before the policy was switched on (`signed-since-<id>`) are not held against anyone.
        An index that is present but unreadable fails closed (TM-R25)."""
        if not incoming_head or incoming_head == held_head:
            return
        from sgit_ai.storage.Vault__Format                    import Vault__Format, FEATURE_SIG_REQUIRED
        from sgit_ai.core.actions.verify.Vault__Signatures    import Vault__Signatures
        from sgit_ai.core.actions.verify.Vault__Key_Fetch     import Vault__Key_Fetch
        from sgit_ai.core.Vault__Errors                       import Vault__Signature_Error
        from sgit_ai.storage.Vault__Scope                     import Vault__Scope
        from sgit_ai.core.actions.status.Vault__Sync__Status  import Vault__Sync__Status
        index_id = str(c.branch_index_file_id or '')
        if not index_id or not os.path.isfile(c.storage.index_path(directory, index_id)):
            return                                                         # no index (single-branch vault): no policy
        index = c.branch_manager.load_branch_index(directory, index_id, read_key)
        if not Vault__Format().has_feature(index, FEATURE_SIG_REQUIRED):
            return
        stop = self.local_history(c, read_key, held_head)                  # what this clone already holds is not incoming
        if incoming_head in stop:
            return                                                         # behind or equal: nothing incoming
        stop |= self.policy_start(c, index)                                 # commits from before the policy was switched on
        bounds = set()
        try:
            bounds = set(Vault__Scope().from_local_config(self._read_local_config(directory, c.storage)).boundary_ids())
        except Exception:
            pass
        Vault__Sync__Status(crypto=self.crypto, api=self.api)._fetch_commit_chain(     # the incoming commits, if absent
            c, c.obj_store, read_key, incoming_head, limit=10000, known=stop | bounds, boundaries=bounds)
        key_fetch = Vault__Key_Fetch(crypto=self.crypto, api=self.api)       # a teammate's key this clone has not seen yet
        report    = Vault__Signatures(crypto=self.crypto, key_fetch=key_fetch).verify_chain(
            c, read_key, incoming_head, stop_at=stop, index=index, boundaries=bounds)
        if report['first_failure']:
            cid, status = report['first_failure']
            raise Vault__Signature_Error(
                f'this vault requires signed commits and commit {cid} is {status}; '
                f'it was refused before anything was changed. Ask the vault owner; if the owner '
                f'relaxes the policy (`sgit vault format --remove-feature signatures-required`), '
                f'try again.')

    def local_history(self, c, read_key: bytes, head: str) -> set:
        """Every commit reachable from `head` that is in the store (all parents). Only
        those are 'already held'; stopping at the head alone made a remote head that is
        an ancestor, or a divergent merge base, count as incoming and dragged
        pre-policy history into the check."""
        from sgit_ai.crypto.PKI__Crypto    import PKI__Crypto
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc    = Vault__Commit(crypto=c.obj_store.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        seen  = set()
        queue = [head] if head else []
        while queue:
            cid = queue.pop()
            if not cid or cid in seen or not c.obj_store.exists(cid):
                continue
            seen.add(cid)
            try:
                queue.extend(str(p) for p in (vc.load_commit(cid, read_key).parents or []) if str(p))
            except Exception:
                continue
        return seen

    def policy_start(self, c, index) -> set:
        """The commit the index records as the policy's start (`signed-since-<id>`), if
        this clone holds it. Not pinned per clone: a pin locked out every clone that had
        not pulled while the owner turned the policy off and on again (the TM-R30
        remedy), and it protected little, since an index that moves the start can only
        come from a read-key holder, who could as well turn the policy off (TM-R01),
        and a replayed older index clears it anyway (TM-R29). Review d3b8eef L2."""
        from sgit_ai.storage.Vault__Format import Vault__Format
        anchor = Vault__Format().sig_anchor_of(index)
        if not anchor:
            return set()
        try:
            return {n for n in os.listdir(os.path.join(str(c.sg_dir), 'bare', 'data')) if n.startswith('obj-cas-imm-' + anchor)}
        except OSError:
            return set()
