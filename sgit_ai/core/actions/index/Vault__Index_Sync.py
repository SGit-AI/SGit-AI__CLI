"""Vault__Index_Sync — the branch index as a shared document, not a local file.

The branch index (bare/indexes/<id>, encrypted) carries every clone branch's
metadata, the branch -> public key mapping and the format gate. Two clients
write it: the CLI and the web UI. Until both merge before writing, the last
writer wins and the loser's entries vanish. This class makes the CLI side
safe whatever the other side does:

  * refresh(): read the remote copy, MERGE it with the local copy (union of
    branches by id; the gate as the server copy has it), save locally, and
    when the merge adds something the remote lacks, write it back with
    compare-and-swap so a concurrent writer is never clobbered.
  * upload(): write with compare-and-swap against the bytes last read, re-read
    and re-merge on conflict.

The gate (format, min_client, features) is the vault owner's decision and
the server copy carries the latest one: a clone's older copy never overrides
it (0.19.0/0.20.0 took the union, so a stale clone kept a removed feature and
wrote it back). Only when the server copy has NO gate fields at all, which is
what a writer that does not know them leaves (the web UI today), does the
local gate come back. The format itself never goes down.
"""
import base64
import json
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.network.api.Vault__API               import Vault__API
from   sgit_ai.schemas.Schema__Branch_Index         import Schema__Branch_Index
from   sgit_ai.storage.Vault__Format                import Vault__Format, FORMAT_2, FEATURE_IDS_128

MAX_CAS_RETRIES = 3


class Vault__Index_Sync(Type_Safe):
    crypto : Vault__Crypto = None
    api    : Vault__API    = None

    # ----------------------------------------------------------------- read
    def read_remote(self, vault_id: str, index_id: str, read_key: bytes) -> tuple:
        """(raw ciphertext, Schema__Branch_Index) or (None, None) when absent/unreadable.
        Raises Vault__Client_Too_Old_Error when the remote gate refuses this client."""
        from sgit_ai.storage.Vault__Format import Vault__Client_Too_Old_Error
        try:
            raw = self.api.read(str(vault_id), f'bare/indexes/{index_id}')
        except Exception:
            return None, None
        if not raw:
            return None, None
        try:
            index = Schema__Branch_Index.from_json(json.loads(self.crypto.decrypt(read_key, raw)))
        except Exception:
            return raw, None
        Vault__Format().check_client(index)
        return raw, index

    # ---------------------------------------------------------------- merge
    def has_gate(self, index: Schema__Branch_Index) -> bool:
        """True when the index carries any gate field. sgit vault format always
        writes an explicit format, so an index without one was last written by a
        client that does not know the fields."""
        if index is None:
            return False
        return index.format is not None or bool(index.min_client) or bool(list(index.features or []))

    def merge(self, local: Schema__Branch_Index, remote: Schema__Branch_Index,
              gate: str = 'remote') -> Schema__Branch_Index:
        """Union of the branches: every branch by id (remote's entry wins for a
        shared id, local fills in fields the remote entry lacks); never loses one.
        The gate (format, min_client, features):
          gate='remote' (default): the server copy's, the owner's latest decision;
                        the local one only when the server copy has no gate fields
                        (dropped by a writer that does not know them).
          gate='local':  `local`'s, an owner's explicit decision (sgit vault format).
        The format is never lowered by a merge."""
        fmt = Vault__Format()
        if local is None:  return remote
        if remote is None: return local
        by_id = {}
        for b in list(local.branches or []) + list(remote.branches or []):
            bid = str(b.branch_id)
            if bid in by_id:
                cur = by_id[bid]; new = b.json()
                for k, v in new.items():
                    if v not in (None, '', [], 0) or k not in cur:
                        cur[k] = v
            else:
                by_id[bid] = b.json()
        if gate == 'local' or not self.has_gate(remote):
            g_format, g_min, g_feat = local.format, (fmt.min_client_of(local) or None), list(fmt.features_of(local))
        else:
            g_format = max(fmt.format_of(local), fmt.format_of(remote))
            g_min    = fmt.min_client_of(remote) or None
            g_feat   = list(fmt.features_of(remote))
            if g_format == 1 and local.format is None and remote.format is None:
                g_format = None                                # keep the on-disk shape of a never-raised vault
        if g_format is not None and int(g_format) >= FORMAT_2 and FEATURE_IDS_128 not in g_feat:
            g_feat.append(FEATURE_IDS_128)
        return Schema__Branch_Index.from_json(dict(
            schema     = str(remote.schema or local.schema or 'branch_index_v1'),
            branches   = list(by_id.values()),
            format     = g_format,
            min_client = g_min,
            features   = sorted(g_feat),
        ))

    def _is_no_write_access(self, error: Exception) -> bool:
        text = str(error)
        return any(t in text for t in ('401', '403', 'Unauthorized', 'Forbidden', 'nauthorised'))

    def _higher_version(self, a: str, b: str) -> str:
        fmt = Vault__Format(); pa, pb = fmt.parse_version(a), fmt.parse_version(b)
        if pa is None: return b or ''
        if pb is None: return a
        return a if pa >= pb else b

    def same(self, a: Schema__Branch_Index, b: Schema__Branch_Index) -> bool:
        if a is None or b is None:
            return a is b
        key = lambda idx: (sorted((str(x.branch_id), json.dumps(x.json(), sort_keys=True)) for x in (idx.branches or [])),
                           Vault__Format().format_of(idx), Vault__Format().min_client_of(idx),
                           sorted(Vault__Format().features_of(idx)))
        return key(a) == key(b)

    # --------------------------------------------------------------- upload
    def encrypt(self, index: Schema__Branch_Index, read_key: bytes) -> bytes:
        return self.crypto.encrypt(read_key, json.dumps(index.json()).encode())

    def upload(self, vault_id: str, index_id: str, read_key: bytes, write_key: str,
               index: Schema__Branch_Index, expected_raw: bytes = None, gate: str = 'remote') -> Schema__Branch_Index:
        """Write the index with compare-and-swap against expected_raw (None = the
        server has none yet: plain write). On a conflict, re-read, merge, retry.
        Returns the index that ended up on the server."""
        current = index; expected = expected_raw
        for _ in range(MAX_CAS_RETRIES):
            op = dict(op='write-if-match' if expected is not None else 'write',
                      file_id=f'bare/indexes/{index_id}',
                      data=base64.b64encode(self.encrypt(current, read_key)).decode('ascii'))
            if expected is not None:
                op['match'] = base64.b64encode(expected).decode('ascii')
            try:
                result = self.api.batch(str(vault_id), write_key, [op])
                conflict, current_b64 = self._cas_conflict(result)
                if not conflict:
                    return current
            except Exception as error:                           # a server that answers a CAS miss with an HTTP error
                if 'conflict' not in str(error).lower() and '409' not in str(error) and '412' not in str(error):
                    raise
                current_b64 = None
            expected, remote = self.read_remote(vault_id, index_id, read_key)
            if expected is None and current_b64:                 # the conflict reply carried the current bytes
                expected = base64.b64decode(current_b64)
            current = self.merge(current, remote, gate=gate) if remote is not None else current
        return current

    def _cas_conflict(self, result) -> tuple:
        """(conflicted, current_b64). The in-memory API reports a conflict as the
        top-level status; the live server returns HTTP 200 with the conflict on the
        operation itself (`results[i].status == 'conflict'`, `current` = the bytes now
        stored). Both are a conflict."""
        result = result or {}
        if str(result.get('status', 'ok')) == 'conflict':
            return True, result.get('current')
        for r in result.get('results') or []:
            if isinstance(r, dict) and str(r.get('status', 'ok')) == 'conflict':
                return True, r.get('current')
        return False, None

    # -------------------------------------------------------------- refresh
    def refresh(self, c, directory: str, write_key: str = None) -> dict:
        """Read remote, merge with local, save locally; push the merge back (CAS) when
        it carries something the remote lacks and a write key is available.
        Returns dict(remote=bool, changed_local=bool, uploaded=bool, restored=int)."""
        read_key = c.read_key; index_id = c.branch_index_file_id
        try:
            local = c.branch_manager.load_branch_index(directory, index_id, read_key)
        except FileNotFoundError:
            local = None
        raw, remote = self.read_remote(c.vault_id, index_id, read_key)
        if remote is None:
            return dict(remote=False, changed_local=False, uploaded=False, restored=0)
        merged = self.merge(local, remote)
        changed_local = not self.same(merged, local)
        if changed_local:
            c.branch_manager.save_branch_index(directory, merged, read_key, index_file_id=index_id)
        restored = len(merged.branches or []) - len(remote.branches or [])
        uploaded = False
        if write_key and not self.same(merged, remote):
            try:
                self.upload(c.vault_id, index_id, read_key, write_key, merged, expected_raw=raw)
                uploaded = True
            except Exception as error:                      # a clone without write access keeps its merge locally
                if not self._is_no_write_access(error):
                    raise
        return dict(remote=True, changed_local=changed_local, uploaded=uploaded, restored=max(restored, 0))
