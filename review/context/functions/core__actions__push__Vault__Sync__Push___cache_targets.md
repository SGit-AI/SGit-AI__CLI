## `_cache_targets` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L538-L561)

**Purpose:** `(targets, server_ids, listing_ok)`: the union of the local cache ids and those the server lists under `bare/cache/`, plus which of them the server holds (deletes are issued only for those) and whether the listing worked (tombstones are kept otherwise).

**Inputs & Assumptions:** `manager`, `directory`, `vault_id`. Host-supplied: the `list_files` result (strings).

**Outputs & Effects:** sorted targets; no writes.

**Block-by-Block:**
```python
# L548-L559
try:
    for file_id in (self.api.list_files(vault_id, 'bare/cache/') or []):
        parts = str(file_id).replace('\\', '/').strip('/').split('/')
        if len(parts) >= 4 and parts[0] == 'bare' and parts[1] == 'cache':
            kind = manager.kind_for_dir_name(parts[2])
            if kind and parts[3].startswith('cch-pid-'):
                server_ids.add((kind, parts[3]))
    listing_ok = True
except Exception: pass
```
- **What:** parse `bare/cache/<value|pointer>/<cch-pid-...>`; anything else is ignored.
- **Establishes:** a server-derived `cache_id` is a single path segment (no `/` after the split; backslashes normalised) beginning `cch-pid-`. It is later used as a filename under `.sg_vault/bare/cache/<kind>/` by `manager.delete/save/load` (`Vault__Storage.cache_path`, L60-L62: `os.path.join(bare_cache_dir, kind, cache_id)`) and as the wire `file_id`. A segment cannot contain `/`; `..` alone does not start with the prefix; other characters (spaces, NUL, very long names) are not filtered: `nothing found` beyond the prefix test.
- **Assumes:** an exception means offline/older server → local set only, `listing_ok=False` (tombstones kept). A host returning `[]` (or ids in a shape the parser rejects, e.g. without the `bare/` prefix — see `Vault__API.list_files` record) yields `listing_ok=True` with no server ids: tombstones for ids the server still holds are then **cleared** (`_reconcile_cache` L443-L445) without a DELETE having been sent. Observation; depends on the live listing shape (open question in `Vault__API.list_files`).

**Cross-Function Dependencies:** callee `Vault__API.list_files` (L347-L358), `Vault__Cache_Manager.list_all` (L250-L255), `kind_for_dir_name` (L67-L73). Caller: `_reconcile_cache` L424.

**Open Questions:** none beyond the listing shape.
