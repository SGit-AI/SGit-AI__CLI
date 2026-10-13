## `batch_read` in sgit_ai/network/api/Vault__API__Static.py (L140-L178)

**Purpose:** The static counterpart of `Vault__API.batch_read`: sniff the layout serially until one object is found, then fan out GETs (8 workers for http, 1 for local — L38-L39) for the rest. Per-object absence never aborts; a dead host raises before the parallel phase.

**Inputs & Assumptions:** `vault_id`, `file_ids`, `failures` (dict | None).

**Outputs & Effects:**
- Returns `{fid: bytes | None}` with **every** requested id present (unlike the live `batch_read`, which omits ids the server did not mention).
- `failures[fid]` = ABSENT for every `None` (via `_record_absent`), including objects that answered a non-404 status (L164-L165) and every id when no layout ever resolved (L174-L177).

**Block-by-Block:**
```python
# L149-L159 (sniff)
if self.layout is None:
    for fid in remaining:
        try: data = self.read(vault_id, fid)
        except Vault__Static_Object_Error: data = None
        payloads[fid] = data
        if data is not None: break
        self._record_absent(fid, failures)
    remaining = [fid for fid in file_ids if fid not in payloads]
```
- **What:** `read` pins `layout` on the first hit. Ids tried before the hit are recorded absent — but note they were tried on *both* layouts by `read`, so that is accurate.
- **Assumes:** a `Vault__Static_Transport_Error` from `read` is the dead-host signal and must propagate (it does, not caught here — test `test_dead_host_aborts_batch_read_loudly`).

```python
# L161-L173 (fan-out)
def fetch_one(fid):
    try: return fid, self._fetch(self._location(self.layout, vault_id, fid))
    except Vault__Static_Object_Error: return fid, None
with ThreadPoolExecutor(max_workers=workers) as executor:
    for fid, data in executor.map(fetch_one, remaining): ...
```
- **What:** GET each remaining id at the pinned layout. A transport error inside a worker propagates out of `executor.map` (not caught).
- **Assumes:** callers verify bytes before writing (content address) — `Vault__Verified_Write` on every download path (`Test_Vault__API__Static__SP1_Integrity::test_object_swap_is_refused`, `test_corrupt_object_is_skipped_not_written`).

**Cross-Function Dependencies:** callees `read`, `_fetch`, `_location`, `_record_absent`. Callers: every `api.batch_read` site when static (pull, status, clone, and push's `_named_ref_absent_on_server`/`_holds` — the last two only matter with a write path, which static has none).

**Open Questions:** none.
