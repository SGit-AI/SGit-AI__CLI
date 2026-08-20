"""Vault__Cache_Reader — the one-request read fast path (contract 08/12 v0 §7).

This is the payoff of the cache layer, and the reference implementation the
SG/Vault client mirrors. It needs only `vault_id` + `read_key` — no clone, no
local vault, no write capability (§4.2) — so it is usable from an edge function
or Lambda that serves one hot record.

Protocol:
  1. compute the candidate cache ids locally (no request)
  2. ONE batch read of {named ref} ∪ {candidates} — breadth, not depth
  3. decrypt, verify the recorded path, compare commit_id against the ref

Correctness never depends on the cache: a miss, a path mismatch (48-bit id
collision) or a stale entry all return a result that tells the caller to fall
back to the ordinary tree walk.
"""
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.network.api.Vault__API              import Vault__API
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager        import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind         import Enum__Cache_Kind
from sgit_ai.safe_types.Enum__Cache_Mutability   import Enum__Cache_Mutability


class Vault__Cache_Reader(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def candidate_ids(self, read_key: bytes, vault_id: str, path: str,
                      kind: Enum__Cache_Kind = None) -> list:
        """[(kind, cache_id)] to probe for `path`.

        Both mutability labels are probed because the label is part of the id
        string but not of the hash, so a reader that does not know how a path was
        declared cannot tell `snw` from `muw` up front. They go in the same batch,
        so this costs extra ops, never an extra round trip.
        """
        manager = Vault__Cache_Manager(crypto=self.crypto, storage=Vault__Storage())
        kinds   = [kind] if kind else [Enum__Cache_Kind.VALUE, Enum__Cache_Kind.POINTER]
        out     = []
        for k in kinds:
            for mut in (Enum__Cache_Mutability.SNW, Enum__Cache_Mutability.MUW):
                out.append((k, manager.cache_id(read_key, vault_id, path, k, mut)))
        return out

    def read_path(self, vault_id: str, read_key: bytes, path: str,
                  kind: Enum__Cache_Kind = None, resolve_pointer: bool = True) -> dict:
        """Resolve `path` through the cache layer in one round trip where possible.

        Returns a dict describing what happened — never raises for a cache miss:
          found        : a usable cache object was located
          fresh        : its commit_id matches the vault's current named head
          source       : 'cache-value' | 'cache-pointer' | None
          content      : bytes, for a value cache (or a resolved blob pointer)
          target_kind  : 'blob' | 'tree', for a pointer
          target_id    : the object id a pointer refers to
          head_commit  : the vault's current head, for the caller's own checks
          round_trips  : requests actually issued
          fallback     : True when the caller must use the ordinary tree walk
        """
        import base64

        manager     = Vault__Cache_Manager(crypto=self.crypto, storage=Vault__Storage())
        ref_file_id = 'ref-pid-muw-' + self.crypto.derive_ref_file_id(read_key, vault_id)
        candidates  = self.candidate_ids(read_key, vault_id, path, kind)

        wanted = [f'bare/refs/{ref_file_id}']
        by_fid = {}
        for k, cache_id in candidates:
            fid = manager.file_id(k, cache_id)
            by_fid[fid] = (k, cache_id)
            wanted.append(fid)

        result = dict(found=False, fresh=False, source=None, content=None,
                      target_kind=None, target_id=None, head_commit='',
                      round_trips=0, fallback=True, path=path)

        try:
            data = self.api.batch_read(vault_id, wanted)          # ONE round trip
        except Exception:
            return result
        result['round_trips'] = 1

        head = ''
        ref_blob = data.get(f'bare/refs/{ref_file_id}')
        if ref_blob:
            try:
                import json as _json
                head = _json.loads(self.crypto.decrypt(read_key, ref_blob)).get('commit_id', '')
            except Exception:
                head = ''
        result['head_commit'] = head

        decoded = []
        for fid, (k, cache_id) in by_fid.items():
            blob = data.get(fid)
            if not blob:
                continue
            try:
                obj = manager.decrypt_object(blob, read_key, k)
            except Exception:
                continue                                          # corrupt — treat as a miss
            if str(obj.path) != path:                             # 48-bit id collision guard
                continue
            decoded.append((k, obj))

        # Prefer a fresh candidate over the first-found one: when D4 has been
        # violated (value AND pointer both present), a stale value must not
        # shadow a fresh pointer the same batch already paid for.
        fresh_first = ([c for c in decoded if bool(head) and str(c[1].commit_id) == head] +
                       [c for c in decoded if not (bool(head) and str(c[1].commit_id) == head)])

        for k, obj in fresh_first:
            if k == Enum__Cache_Kind.VALUE:
                try:
                    content = base64.b64decode(str(obj.value_b64)) if obj.value_b64 else b''
                except Exception:
                    continue                                      # malformed base64 — a miss,
                                                                  # never an exception (M1)
            result['found']  = True
            result['fresh']  = bool(head) and str(obj.commit_id) == head
            result['source'] = 'cache-value' if k == Enum__Cache_Kind.VALUE else 'cache-pointer'

            if k == Enum__Cache_Kind.VALUE:
                result['content']  = content
                result['fallback'] = not result['fresh']
                return result

            result['target_kind'] = obj.target_kind.value
            result['target_id']   = str(obj.target_id)
            if resolve_pointer and obj.target_kind.value == 'blob' and obj.target_id:
                try:
                    blob_bytes = self.api.read(vault_id, f'bare/data/{obj.target_id}')
                    result['round_trips'] += 1                    # the pointer's +1
                    if blob_bytes:
                        result['content'] = self.crypto.decrypt(read_key, blob_bytes)
                except Exception:
                    pass
                if result['content'] is None:
                    # The blob read failed or came back empty: a fresh pointer with
                    # no content must still send the caller to the tree walk (H3) —
                    # fallback=False with content=None would serve nothing for a
                    # file that exists.
                    result['fallback'] = True
                    return result
            result['fallback'] = not result['fresh']
            return result

        return result                                             # miss → caller falls back
