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
from   sgit_ai.storage.Vault__Index_Reader          import Vault__Index_Reader, TAG_CLOCK_SKEW_MS

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
        index = self.decode(raw, read_key)
        if index is None:
            return raw, None
        Vault__Format().check_client(index)
        return raw, index

    def decode(self, raw: bytes, read_key: bytes):
        """The index inside server bytes, or None when they do not decrypt or parse."""
        try:
            return Vault__Index_Reader().parse(json.loads(self.crypto.decrypt(read_key, raw)))
        except Exception:
            return None

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
        reader        = Vault__Index_Reader()
        tags, carried = reader.resolve(reader.entries(local) + reader.entries(remote))   # entries it cannot read included (B1)
        return Schema__Branch_Index.from_json(dict(
            schema     = str(remote.schema or local.schema or 'branch_index_v1'),
            branches   = list(by_id.values()),
            format     = g_format,
            min_client = g_min,
            features   = sorted(g_feat),
            tags         = tags,
            carried_tags = carried,
        ))

    def merge_tags(self, local_tags, remote_tags, now_ms: int = None) -> list:
        """One entry per name: the later (timestamp_ms, tag_id) wins, tombstones
        included, so a delete or a re-point made anywhere survives every stale copy.
        A clone that does not know tags drops the field; ours bring it back.

        The timestamp is the writer's claim, so an entry dated beyond now + a day
        of clock skew loses to every entry that is not: a far-future entry (or
        tombstone) can no longer pin or delete a name for good (TM-R06).
        The rule itself lives in Vault__Index_Reader.resolve, which also handles the
        entries this version cannot read (`merge` and `with_tag_entry` use it)."""
        return Vault__Index_Reader().resolve(list(local_tags or []) + list(remote_tags or []), now_ms=now_ms)[0]

    def with_tag_entry(self, index: Schema__Branch_Index, entry) -> Schema__Branch_Index:
        """`index` with `entry` merged in by the per-name rule, carried entries included:
        an entry this version cannot read can still win against a new one (B1)."""
        reader = Vault__Index_Reader()
        index.tags, index.carried_tags = reader.resolve(reader.entries(index) + [entry])
        return index

    def live_tags(self, index) -> dict:
        """{name: tag_id} for every tag not deleted."""
        return {str(t.name): str(t.tag_id) for t in (getattr(index, 'tags', None) or []) if not t.deleted}

    def tag_changes(self, before, after) -> list:
        """[(name, old_tag_id or '', new_tag_id or '')] for tags that appeared, moved or went."""
        a, b = self.live_tags(before), self.live_tags(after)
        return [(n, a.get(n, ''), b.get(n, '')) for n in sorted(set(a) | set(b)) if a.get(n) != b.get(n)]

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
                           sorted(Vault__Format().features_of(idx)),
                           sorted(json.dumps(t.json(), sort_keys=True) for t in (getattr(idx, 'tags', None) or [])),
                           sorted(str(c) for c in (getattr(idx, 'carried_tags', None) or [])))
        return key(a) == key(b)

    # --------------------------------------------------------------- upload
    def encrypt(self, index: Schema__Branch_Index, read_key: bytes) -> bytes:
        return self.crypto.encrypt(read_key, Vault__Index_Reader().serialize(index))      # carried entries go back (B1)

    def upload(self, vault_id: str, index_id: str, read_key: bytes, write_key: str,
               index: Schema__Branch_Index, expected_raw: bytes = None, gate: str = 'remote') -> Schema__Branch_Index:
        """Write the index with compare-and-swap against expected_raw (None = the
        server has none yet: plain write). On a conflict, re-read, merge, retry.
        Returns the merged index (this clone's copy). What is written leaves out the
        entries that clash by name with the server's (`server_copy`, S1)."""
        current = index; expected = expected_raw
        remote  = self.decode(expected_raw, read_key) if expected_raw is not None else None
        for _ in range(MAX_CAS_RETRIES):
            op = dict(op='write-if-match' if expected is not None else 'write',
                      file_id=f'bare/indexes/{index_id}',
                      data=base64.b64encode(self.encrypt(self.server_copy(current, remote), read_key)).decode('ascii'))
            if expected is not None:
                op['match'] = base64.b64encode(expected).decode('ascii')
            try:
                result = self.api.batch(str(vault_id), write_key, [op])
                conflict, current_b64 = self._cas_conflict(result)
                if not conflict:
                    self.require_written(result, 'the branch index')      # anything but 'ok' is not a write
                    return current
            except Exception as error:                           # a server that answers a CAS miss with an HTTP error
                if 'conflict' not in str(error).lower() and '409' not in str(error) and '412' not in str(error):
                    raise
                current_b64 = None
            expected, remote = self.read_remote(vault_id, index_id, read_key)
            if expected is None and current_b64:                 # the conflict reply carried the current bytes
                expected = base64.b64decode(current_b64)
            current = self.merge(current, remote, gate=gate) if remote is not None else current
        raise RuntimeError(f'the branch index changed on the server {MAX_CAS_RETRIES} times while this write was '
                           f'retried; nothing was written. Try again.')          # never report a write that did not happen

    # ------------------------------------------------------- name clashes
    def name_clashes(self, index: Schema__Branch_Index, remote: Schema__Branch_Index) -> dict:
        """{branch_id: name} for this clone's named branches the server does not have,
        whose name a different named branch on the server already uses, with another ref:
        a branch created here while a teammate pushed one with the same name (`branch new`
        saw only this clone's index, review S11). Its commits would land on a ref no
        server entry names."""
        if index is None or remote is None:
            return {}
        named        = lambda b: str(getattr(b.branch_type, 'value', b.branch_type)) == 'named' and bool(b.name)
        remote_ids   = {str(b.branch_id) for b in (remote.branches or [])}
        remote_named = {}
        for b in remote.branches or []:
            if named(b):
                remote_named.setdefault(str(b.name), set()).add(str(b.head_ref_id or ''))
        return {str(b.branch_id): str(b.name) for b in (index.branches or [])
                if named(b) and str(b.branch_id) not in remote_ids and str(b.name) in remote_named
                and str(b.head_ref_id or '') not in remote_named[str(b.name)]}    # the same ref is the same branch

    def server_copy(self, index: Schema__Branch_Index, remote: Schema__Branch_Index) -> Schema__Branch_Index:
        """`index` without the entries that clash by name with the server's (and the clone
        branches made for them). Those stay in this clone's own copy until it renames them
        (sgit branch rename); everything else is written. Refusing the whole merge left a
        clone stuck: pull swallowed the error, so it never saw new branches, tags or keys
        again, and `tag create` failed on it (review eed8084 S1)."""
        clashes = self.name_clashes(index, remote)
        if not clashes:
            return index
        remote_ids = {str(b.branch_id) for b in (remote.branches or [])}
        data = index.json()
        data['branches'] = [b for b in data.get('branches') or []
                            if str(b.get('branch_id')) not in clashes and
                               not (str(b.get('creator_branch') or '') in clashes and str(b.get('branch_id')) not in remote_ids)]
        return Schema__Branch_Index.from_json(data)

    def refuse_name_clash(self, index: Schema__Branch_Index, remote: Schema__Branch_Index, branch_id: str) -> None:
        """Push: refuse before anything is written when the branch being pushed has a name
        another branch on the server already uses. Its commits would land on a ref no
        index entry names, invisible to everyone (review eed8084 S1)."""
        name = self.name_clashes(index, remote).get(str(branch_id))
        if name:
            from sgit_ai.core.Vault__Errors import Vault__Push_Conflict_Error
            raise Vault__Push_Conflict_Error(
                f'a branch named {name!r} already exists on the server (a teammate created one with the same name); '
                f'nothing was written. Rename yours, then push: sgit branch rename {name} <new-name>')

    def require_written(self, result, what: str) -> None:
        """Raise unless the server reports every operation written ('ok'). Treating any
        answer other than 'conflict' as success let a tag or index write report success
        without writing (review d3b8eef)."""
        result = result or {}
        failed = [r for r in (result.get('results') or []) if isinstance(r, dict) and str(r.get('status', 'ok')) != 'ok']
        if failed or str(result.get('status', 'ok')) not in ('ok', ''):
            first = failed[0] if failed else result
            raise RuntimeError(f'the server did not write {what} ({first.get("status")} {first.get("message", "")}'.rstrip()
                               + '); nothing was changed')

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
            return dict(remote=False, changed_local=False, uploaded=False, restored=0, tags_changed=[], clashes=[])
        merged = self.merge(local, remote)
        Vault__Index_Reader().warn_new(local, merged)                # once, when this clone first sees an entry
        tags_changed  = self.tag_changes(local, merged) if local is not None else []
        changed_local = not self.same(merged, local)
        if changed_local:
            c.branch_manager.save_branch_index(directory, merged, read_key, index_file_id=index_id)
        restored = len(merged.branches or []) - len(remote.branches or [])
        uploaded = False
        clashes  = sorted(set(self.name_clashes(merged, remote).values()))
        if write_key and not self.same(self.server_copy(merged, remote), remote):
            try:
                self.upload(c.vault_id, index_id, read_key, write_key, merged, expected_raw=raw)
                uploaded = True
            except Exception as error:                      # a clone without write access keeps its merge locally
                if not self._is_no_write_access(error):
                    raise
        return dict(remote=True, changed_local=changed_local, uploaded=uploaded, restored=max(restored, 0),
                    tags_changed=tags_changed, clashes=clashes)
