## `_guard_working_tree` in sgit_ai/workflow/pull/Step__Pull__Merge.py (L269-L295)

**Purpose:** "Uncommitted work must survive a pull." Scans the working copy, runs `Vault__Pull__Guard.dirty_paths` + `plan`, raises `Vault__Dirty_Working_Tree_Error` **before any write** when the merge would overwrite a dirty file, and returns the carry-over list the caller excludes from the write set.

**Inputs & Assumptions:** `ours_map` (HEAD tree), `merged_map` (what the merge would write); `read_key` for `blob_hash`; `local_config.sparse`.

**Outputs & Effects:** returns `plan['carry_over']`; progress warnings per carried path (L293-L294); raises on `blocked` (L291-L292). No writes.

**Block-by-Block:**

```python
# L279-L286
def blob_hash(blob_id):
    try:
        if read_key is None or not obj_store.exists(blob_id): return ''
        return sync.crypto.content_hash(sync.crypto.decrypt(read_key, obj_store.load(blob_id)))
    except Exception:
        return ''
```
- **What:** The incoming file's real content hash from the decrypted blob (comment L280). `''` = cannot prove ⇒ `plan` blocks the untracked collision.

```python
# L288-L292
dirty = guard.dirty_paths(directory, ours_map, scan, obj_store=obj_store, sparse=sparse)
plan  = guard.plan(dirty, ours_map, merged_map, scan, blob_hash_fn=blob_hash)
if plan['blocked']:
    raise Vault__Dirty_Working_Tree_Error(guard.message(plan['blocked']))
```

**Cross-Function Dependencies:**
- Callers (all before their checkout): fast-forward L96 → checkout L99; three-way L126 → checkout L129; `_take_rewind` L233 → checkout L235. Each builds `apply_map = {p: e for p, e in …map.items() if p not in kept_dirty}` (L98, L128, L234).
- Callee `_scan_local_directory` (raises on unreadable files: pull refuses rather than treating them as deleted — `Vault__Sync__Base.py:L442-L445`).
- Note on ordering across steps: by the time this runs, `Step__Pull__Fetch_Missing._accept` has already written the local named ref and baseline (see `pull` record).
- Tests: `tests/unit/workflow/pull/test_Pull__Dirty_Working_Tree.py::test_edit_to_a_file_the_incoming_commit_changes_refuses_before_writing`, `::test_dirty_untouched_file_survives_a_three_way_merge`.

**Open Questions:** none.

---

## `execute` / `_take_rewind` in sgit_ai/workflow/pull/Step__Pull__Merge.py (L20-L202, L204-L267) — summary only (merge logic is outside this slice; the write order is in slice)

- Writes of the **clone** ref: L101 (fast-forward, after checkout L99-L100), L171 (merge commit, after `create_commit` L170), L261 in `_take_rewind` (after checkout L235-L236 and optional `create_commit` L259).
- Conflict path: no ref write; writes conflict files and `merge_state` (L136-L143).
- Signing: the merge commit is signed with this clone's local private key when present (L151-L159; `load_private_key_locally` reads `.sg_vault/local/<key_id>.pem`, `Vault__Key_Manager.py:L63-L67`), else a warning and an **unsigned** merge commit (L159) — which a teammate under `signatures-required` will refuse on their pull. Same in `_take_rewind` L246-L258.
- Rewind merge: `base = lca(clone, rewound_from)` (L216); a conflict between own work and the rewind refuses before any write (L228-L232).
