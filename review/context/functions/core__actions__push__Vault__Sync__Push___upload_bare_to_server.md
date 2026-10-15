## `_upload_bare_to_server` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L774-L818)

**Purpose:** Bootstrap or resync: walk `.sg_vault/bare/` and upload **every regular file** under it to the server with a plain `write` (large ones via multipart), path relative to `.sg_vault/` as the `file_id`. Used on a first push (L140) and on a resync when the server appears to lack the vault or the named ref (L110).

**Inputs & Assumptions:**
- `directory`, `vault_id`, `write_key`, `storage`, `read_key` (unused beyond the signature).
- Local tree: `bare/data/*` (objects), `bare/refs/*` (every ref file, the named ref at its **local** head), `bare/indexes/*`, `bare/keys/*` (public keys; and, on a vault created before 10/09, the legacy named-branch **private** key — TM-R27; the row says it stays until `vault move`), `bare/cache/*`, `bare/branches/*`, `bare/pending/*` — whatever exists.
- Precondition: the caller decided the server is empty or missing the ref (`_is_first_push`, `_server_has_named_ref`) — trust in a host listing, see those records.

**Outputs & Effects:**
- Host writes: a plain `write` per file (no CAS), including the **named ref** and the **branch index** — the only two paths elsewhere guarded by compare-and-swap. On a true first push nothing is overwritten; on a resync triggered by a host listing, everything the host holds under those ids is replaced by this clone's copies.
- Fallback: on any batch failure, one-by-one `write`s (L816-L818, warning to stderr).
- Returns None; no local writes.

**Block-by-Block:**
```python
# L788-L803
for root, dirs, files in os.walk(bare_dir):
    for filename in files:
        rel_path = os.path.relpath(full_path, storage.sg_vault_dir(directory)).replace(os.sep, '/')
        data = Vault__Path_Guard().read_regular(full_path)       # O_NOFOLLOW (L4)
        if data is None: continue
        if len(data) > LARGE_BLOB_THRESHOLD: large_files.append((rel_path, data))
        else: batch_ops.append(dict(op='write', file_id=rel_path, data=b64(data)))
```
- **What:** regular files only (`read_regular` returns None for links/FIFOs/devices, raises `Vault__Unreadable_File_Error` on EACCES etc., Vault__Path_Guard.py:L183-L208 — the raise propagates and fails the push).
- **Assumes:** everything under `bare/` belongs on the server. Nothing filters by name or kind: `nothing found` (the threat model lists `bare/keys/<legacy private key>` as readable by read-key holders anyway, TM-R27).

```python
# L807-L818
for file_id, data in large_files:
    if not batch._upload_large(vault_id, file_id, data, write_key): batch_ops.append(write)
if batch_ops:
    try: batch.execute_batch(vault_id, write_key, batch_ops)
    except Exception as e: ...; batch.execute_individually(vault_id, write_key, batch_ops)
```
- **What:** large files multipart (any `bare/...` path, not only content-addressed); then the batch. `execute_batch` orders `bare/refs/` ops last (Vault__Batch.py:L282-L284) so refs land after objects.
- **Assumes:** `execute_batch`'s `_checked` accepts the host's `ok`; the fallback's result is self-reported.

**Cross-Function Dependencies:** callees `Vault__Path_Guard.read_regular`, `Vault__Batch._upload_large/execute_batch/execute_individually`, `Vault__Storage.bare_dir/sg_vault_dir`. Callers: `push` L110 (resync), L140 (first push). Tests: `test_Vault__Sync__Push__Coverage.py::test_upload_bare_to_server_no_dir_returns_line_400`, `test_upload_bare_batch_exception_fallback_lines_430_432`, `test_push_resynced_when_is_first_push_true_lines_93_95`.

**Open Questions:**
- unclear; whether the resync path (L106-L111) is still needed now that `_is_first_push`/`_server_has_named_ref` fail on listing errors — the remaining trigger is a truthful or hostile empty listing.
