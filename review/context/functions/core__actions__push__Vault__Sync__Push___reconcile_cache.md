## `_reconcile_cache` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L402-L536)

**Purpose:** After the ref is durable, bring every cache object (`bare/cache/value/*`, `bare/cache/pointer/*`) in line with the new head: tombstoned ones are deleted on the server, duplicates resolved, each live one rebuilt for its recorded path and rewritten (plain `write`) or deleted (`delete`) when its path is gone. **Never raises** (L534-L536): cache failure degrades to staleness.

**Inputs & Assumptions:**
- `directory`, `vault_id`, `read_key`, `write_key`, `commit_id` (the new head), `obj_store`, `storage`, optional `tree_id`/`clone_flat` (already flattened by `push`), `pki`, `on_progress`, `use_batch`.
- Implicit: local cache folder (`manager.list_all`), local tombstones, **the server's listing** (`_cache_targets` → `api.list_files(vault_id, 'bare/cache/')`), and **server-held cache objects** fetched and decrypted (`_fetch_cache_object`, Vault__Sync__Base.py:L52-L68) when absent locally.
- Precondition: the caller has verified the server head equals the local head when called from the "nothing to push" path (`push` L116-L122) so that a stale clone does not delete caches another client just published (comment L112-L115, review 08/14 #2). On the pushed path the head was just written.

**Outputs & Effects:**
- Host writes: `DELETE bare/cache/<kind>/<id>` for tombstoned ids the server holds (L438-L441), for duplicates (L481-L483), and for objects whose path is gone (L505-L508); `WRITE` with freshly encrypted objects (L512-L517). All plain ops (no CAS: cache objects are "derived and non-authoritative", Vault__Cache_Manager.py:L218-L221).
- Local writes: `manager.delete`/`manager.save` under `.sg_vault/bare/cache/...`; tombstones cleared only after the ops landed (L529-L530) and only when the listing succeeded (`listing_ok`, L443-L445).
- Returns `{cache_updated, cache_deleted}`; `{0, 0}` on any exception (with a progress warning, L535).

**Block-by-Block:**

```python
# L422-L426
manager    = Vault__Cache_Manager(crypto=self.crypto, storage=storage)
tombstoned = manager.tombstoned_ids(directory)
targets, server_ids, listing_ok = self._cache_targets(manager, directory, vault_id)
if not targets and not tombstoned: return dict(cache_updated=0, cache_deleted=0)
```
- **What:** the union of local and server-listed cache ids (D6: heal entries written by other clients).
- **Assumes:** the server's listing names real cache objects; `_cache_targets` parses `bare/cache/<kind>/<cch-pid-...>` and keeps only known kinds and the `cch-pid-` prefix (L551-L556). A listed id this clone does not hold is **fetched from the server and decrypted** (L465-L470) to learn its `path`.

```python
# L436-L445  tombstones
for kind, cache_id in [t for t in targets if t in tombstoned]:
    manager.delete(directory, kind, cache_id)
    if (kind, cache_id) in server_ids: operations.append(DELETE manager.file_id(kind, cache_id)); deleted += 1
    cleared.add((kind, cache_id))
if listing_ok: cleared |= set(t for t in tombstoned if t not in targets)
```
- **Establishes:** a `cache rm` intent reaches the server as a DELETE and is not resurrected by the listing (review 08/14 #1).

```python
# L461-L471  load (local or from the server)
for kind, cache_id in live_targets:
    existing = manager.load(directory, kind, cache_id, read_key)
    if existing is None:
        existing = self._fetch_cache_object(manager, vault_id, kind, cache_id, read_key); from_server = ...
```
- **What:** `_fetch_cache_object` = `api.batch_read` + `manager.decrypt_object` (AES-GCM under the read key, then `Schema__Cache_Value/Pointer.from_json`, Vault__Cache_Manager.py:L173-L176); any failure → None.
- **Assumes:** a server cache object that decrypts is authentic. AES-GCM authenticates against anyone **without** the read key; a read-key holder (A3) with host access can mint one (TM-R01 class). Its `path` (L490) then drives `rebuild_for_path` (outside this slice) and the resulting `file_id = manager.file_id(kind, cache_id)` (L504) — the id came from the server listing. Nothing checks that the object's `path` corresponds to its id: `nothing found` (`Vault__Cache_Manager.resolve_duplicates` L476-L477 handles two objects for one path, not a mismatch).

```python
# L486-L517  rebuild and write
blob_fetcher = self._make_blob_fetcher(vault_id)      # api.read of bare/data/<blob> → bytes or None (Vault__Sync__Base.py:L70-L78)
obj = self._rebuild_cache_object(manager, sub_tree, kind, path, commit_id, tree_id, clone_flat, obj_store, read_key, existing, blob_fetcher)
...
elif from_server and obj.json() == existing.json(): continue
else:
    manager.save(directory, kind, cache_id, obj, read_key)
    ciphertext = manager.encrypt_object(obj, read_key)
    operations.append(WRITE file_id data=b64(ciphertext)); updated += 1
```
- **What:** rebuild from the head; the rebuilt object may embed **blob content** fetched from the server by `blob_fetcher` (sparse clones).
- **Assumes:** `blob_fetcher`'s bytes are verified before use. `_make_blob_fetcher` returns `api.read(...)` raw (Vault__Sync__Base.py:L73-L77) with **no content-address check** in this slice; whether `Vault__Cache_Manager.rebuild_for_path` verifies them was not read: open question. If not, a hostile host's blob bytes would be re-encrypted into a cache value and written back to the host under this clone's key — the "laundering" shape TM-F01 describes for move auto-repair. Recorded as an open question, not a finding.

```python
# L519-L527
if operations:
    batch = Vault__Batch(crypto=self.crypto, api=self.api)
    if use_batch:
        try: batch.execute_batch(vault_id, write_key, operations)
        except Exception: batch.execute_individually(vault_id, write_key, operations)
    else: batch.execute_individually(..., atomic_moves=False)
```
- **What:** plain writes/deletes; a conflict is impossible (no CAS op); any failure → one-by-one; a final failure is swallowed by the outer `except` (L534).

**Cross-Function Dependencies:**
- Callees: `_cache_targets` (L538-L561), `_rebuild_cache_object` (L563-L580 → `Vault__Cache_Manager.rebuild_for_path`, not read), `Vault__Sync__Base._fetch_cache_object` L52-L68, `_make_blob_fetcher` L70-L78; `Vault__Cache_Manager.list_all/load/save/delete/encrypt_object/decrypt_object/tombstoned_ids/clear_tombstones/resolve_duplicates` (Vault__Cache_Manager.py); `Vault__Batch.execute_batch/execute_individually`.
- Callers: `push` L125 (nothing-to-push, after the server-head check), L180 (after pull, heads equal), L376 (after the ref write, unscoped only).
- Tests: `tests/unit/core/actions/push/test_Vault__Sync__Push__Cache_Reconcile.py` (value/pointer rebuild, delete on path gone, server upload, fail-soft).

**Open Questions:**
- unclear; need to inspect `Vault__Cache_Manager.rebuild_for_path` to know whether bytes from `blob_fetcher` (unverified `api.read`) are checked against the blob id before being embedded in a cache value.
- unclear; need to inspect `rebuild_for_path`/`resolve_duplicates` for how a server-supplied cache object whose `path` names a file outside the head is treated (expected: `obj is None` → DELETE, L505-L508).
