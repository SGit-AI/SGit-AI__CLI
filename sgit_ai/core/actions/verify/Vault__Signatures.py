"""Vault__Signatures — verify the ECDSA signature on commits.

Where the public key comes from, in order: the commit's own author_key_id
(bare/keys/<id>, written since the canonical signing form), then the branch
index's branch -> public_key_id mapping (older commits). A commit with neither
is 'no-key'; one without a signature is 'unsigned'; a signature that does not
verify is 'bad'. Nothing here writes.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                   import PKI__Crypto
from   sgit_ai.storage.Vault__Commit                import Vault__Commit

VERIFIED = 'verified'
BAD      = 'bad'
UNSIGNED = 'unsigned'
NO_KEY   = 'no-key'
MISSING  = 'missing'


class Vault__Signatures(Type_Safe):
    crypto : Vault__Crypto = None

    def _key_for(self, c, read_key: bytes, commit, index) -> object:
        kid = str(commit.author_key_id) if commit.author_key_id else ''
        if not kid and index is not None and commit.branch_id:
            meta = c.branch_manager.get_branch_by_id(index, str(commit.branch_id))
            kid  = str(meta.public_key_id) if (meta and meta.public_key_id) else ''
        if not kid or not c.key_manager.key_exists(kid):
            return None
        try:
            return c.key_manager.load_public_key(kid, read_key)
        except Exception:
            return None

    def status_of(self, c, read_key: bytes, commit_id: str, index=None, vc: Vault__Commit = None) -> str:
        vc = vc or Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        if not c.obj_store.exists(commit_id):
            return MISSING
        commit = vc.load_commit(commit_id, read_key)
        if not commit.signature:
            return UNSIGNED
        key = self._key_for(c, read_key, commit, index)
        if key is None:
            return NO_KEY
        return VERIFIED if vc.verify_commit_signature(commit, key) else BAD

    def verify_chain(self, c, read_key: bytes, head: str, stop_at: set = None,
                     limit: int = 0, index=None, boundaries: set = None) -> dict:
        """Walk from head (all parents) and classify every commit reached. Commits in
        stop_at are not classified and not expanded (what the clone already holds);
        commits in boundaries are classified but not expanded (a shallow clone's
        history stops there). limit 0 = all.
        Returns dict(total, counts{status: n}, by_status{status: [ids]}, first_failure)."""
        vc = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        if index is None:
            try:
                index = c.branch_manager.load_branch_index(self._directory_of(c), c.branch_index_file_id, read_key)
            except Exception:
                index = None
        stop  = set(stop_at or []); bounds = set(boundaries or [])
        seen  = set(); queue = [head] if head else []
        by    = {VERIFIED: [], BAD: [], UNSIGNED: [], NO_KEY: [], MISSING: []}
        first_failure = None
        while queue:
            cid = queue.pop(0)
            if not cid or cid in seen or cid in stop:
                continue
            seen.add(cid)
            if limit and len(seen) > limit:
                break
            status = self.status_of(c, read_key, cid, index=index, vc=vc)
            by[status].append(cid)
            if status != VERIFIED and first_failure is None:
                first_failure = (cid, status)
            if status == MISSING or cid in bounds:
                continue
            commit = vc.load_commit(cid, read_key)
            queue.extend(str(p) for p in (commit.parents or []) if str(p))
        return dict(total=len(seen), counts={k: len(v) for k, v in by.items()}, by_status=by,
                    first_failure=first_failure)

    def _directory_of(self, c) -> str:
        import os
        return os.path.dirname(str(c.sg_dir))
