"""Vault__Ref_Guard — the named branch only ever moves forward.

The remote named ref is an encrypted pointer the host (or any writer with
`push --force`) can move anywhere. Every clone remembers the last remote head
it fully fetched; a new remote head that does not descend from it is a
rewind: a rollback, a rewritten history, or a host replaying an old ref.
Status reports it; pull refuses it until `--accept-rewind`.
"""
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                   import PKI__Crypto
from   sgit_ai.storage.Vault__Commit                import Vault__Commit

FORWARD  = 'forward'      # new head descends from the last known head (or equals it)
REWOUND  = 'rewound'      # new head is an ancestor of the last known head, or an unrelated lineage
UNKNOWN  = 'unknown'      # could not decide within the fetch limit / offline
LOCAL_WALK_LIMIT = 100000


class Vault__Ref_Guard(Type_Safe):
    crypto : Vault__Crypto = None

    def is_ancestor(self, c, read_key: bytes, ancestor: str, descendant: str, boundaries: set = None) -> bool:
        """True when `ancestor` is reachable from `descendant` through LOCAL commits."""
        if not ancestor or not descendant:
            return False
        if ancestor == descendant:
            return True
        vc = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(), object_store=c.obj_store, ref_manager=c.ref_manager)
        seen = set(); queue = [descendant]
        while queue and len(seen) < LOCAL_WALK_LIMIT:
            cid = queue.pop()
            if cid in seen or not c.obj_store.exists(cid):
                continue
            seen.add(cid)
            if boundaries and cid in boundaries:
                continue
            try:
                commit = vc.load_commit(cid, read_key)
            except Exception:
                continue
            for p in (commit.parents or []):
                p = str(p)
                if p == ancestor:
                    return True
                if p and p not in seen:
                    queue.append(p)
        return False

    def classify(self, c, read_key: bytes, remote_head: str, last_known: str,
                 connected: bool, reached_known: bool, boundaries: set = None) -> str:
        """Given the outcome of the fetch walk from remote_head (connected = every
        commit it needed is local; reached_known = it met last_known), decide."""
        if not last_known or not remote_head or remote_head == last_known:
            return FORWARD
        if reached_known:
            return FORWARD
        if self.is_ancestor(c, read_key, remote_head, last_known, boundaries):
            return REWOUND                                       # a rollback: the new head is in our past
        if connected:
            return REWOUND                                       # a complete, unrelated lineage: rewritten history
        return UNKNOWN

    def message(self, remote_head: str, last_known: str) -> str:
        return (f'the remote named branch was rewound or rewritten: it pointed at {last_known} the '
                f'last time this clone saw it and now points at {remote_head}, which does not descend '
                f'from it. If this was a deliberate `sgit push --force`, run `sgit pull --accept-rewind`; '
                f'otherwise treat it as tampering and check with the vault owner. Nothing was changed.')
