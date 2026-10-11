## `dirty_paths` in sgit_ai/core/actions/pull/Vault__Pull__Guard.py (L30-L55)

**Purpose:** `{path: 'modified'|'deleted'|'untracked'}` for the working tree against the clone HEAD tree, measured the way `sgit status` measures it (content hash). It feeds `plan`, which decides whether a pull may write.

**Inputs & Assumptions:**
- `directory`: unused in the body (kept for signature).
- `ours_map` (dict): the HEAD tree flattened — `{path: {blob_id, size, content_hash, ...}}`. Trust: **semi-trusted** — decrypted tree entries written by whoever authored the commit; `content_hash` is the author's claim (docstring of `plan` L67-L70 says so explicitly).
- `local_scan` (dict): `Vault__Sync__Base._scan_local_directory` output — `{path: {size, content_hash}}` of regular files on disk, symlinks skipped, tracked paths under links carried from HEAD (L455-L457 of Base). Trust: trusted (computed locally), but see the link carry-over: a tracked path hidden behind a link is reported with its *committed* hash, so it reads "clean" here (`_keep_tracked_under_links` L467-L477).
- `obj_store`, `sparse`: on a sparse clone an unfetched blob makes a tracked-but-absent file *not* dirty (L41-L43).

**Outputs & Effects:** returns dict; no effects.

**Block-by-Block:**

```python
# L38-L45
for path, entry in ours_map.items():
    local = local_scan.get(path)
    if local is None:
        if sparse and obj_store is not None and not obj_store.exists(entry.get('blob_id', '')):
            continue
        dirty[path] = 'deleted'
        continue
```
- **What:** tracked, not on disk ⇒ deleted, unless sparse-and-never-fetched.
- **Assumes:** the scan's absence means absence. `_scan_local_directory` raises `Vault__Unreadable_File_Error` rather than omitting an unreadable file (L442-L448 of Base, `unreadable_out is None` on the pull path, `Step__Pull__Merge._guard_working_tree` L275 passes none), so "unreadable" never reaches here as "deleted".

```python
# L46-L51
tracked_hash = entry.get('content_hash', '')
if tracked_hash:
    if tracked_hash != local.get('content_hash', ''):
        dirty[path] = 'modified'
elif local.get('size', -1) != entry.get('size', -2):
    dirty[path] = 'modified'
```
- **What:** hash comparison, falling back to size when the tree carries no hash (older entries).
- **Assumes:** the tree's `content_hash` matches the blob's real content. A commit whose entry lies about the hash makes an *unmodified* file read `modified` (blocks or carries over) or a modified file read clean (if the lie matches the new content). `plan` refuses to trust the hash for the *untracked* case (L89-L92) and proves it from the blob; for the tracked case it compares blob ids only (L77-L78), so a lying hash in HEAD costs at most a wrong dirty/clean classification of the user's own file, not a silent overwrite by incoming content (an incoming change is detected by `merged_blob != ours_blob`, not by hash).

```python
# L52-L54
for path in local_scan:
    if path not in ours_map:
        dirty[path] = 'untracked'
```
- **What:** on disk, not in HEAD ⇒ untracked.

**Cross-Function Dependencies:**
- Callers: `Step__Pull__Merge._guard_working_tree` L289 (fast-forward, three-way, and accepted-rewind paths all call `_guard_working_tree` before any checkout: L96, L126, L233 of the step).
- Shared state: none.
- Invariant coupling: "Dirty is measured exactly as sgit status measures it" (module docstring L21-L22) — both use `_scan_local_directory`'s `content_hash`.
- Tests: `tests/unit/workflow/pull/test_Pull__Dirty_Working_Tree.py::test_dirty_paths_matches_status_semantics`, `::test_the_reported_case__edit_to_an_untouched_file_survives`.

**Open Questions:** none.
