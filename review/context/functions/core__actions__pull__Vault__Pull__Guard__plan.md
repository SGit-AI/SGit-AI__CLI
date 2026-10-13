## `plan` in sgit_ai/core/actions/pull/Vault__Pull__Guard.py (L57-L94)

**Purpose:** For each dirty path, decide `carry_over` (the merge must not write it) or `blocked` (the pull refuses). Called before any working-copy write on every pull path.

**Inputs & Assumptions:**
- `dirty`: from `dirty_paths`.
- `ours_map`, `merged_map`: HEAD tree and the tree the merge would produce. Trust: semi-trusted (authored content).
- `local_scan`: trusted.
- `blob_hash_fn`: `Step__Pull__Merge._guard_working_tree.blob_hash` (L279-L286): decrypts the local blob and hashes its plaintext; `''` on any failure or when the blob is not local.

**Outputs & Effects:** `dict(carry_over=[...], blocked=[(path, reason)])`; no effects.

**Block-by-Block:**

```python
# L76-L80 (modified)
if merged_blob == ours_blob:
    carry_over.append(path)
else:
    blocked.append((path, 'your uncommitted edit would be overwritten'))
```
- **What:** "changed by the merge" = blob id differs between HEAD and merged.
- **Assumes:** blob ids are content addresses, so equal ids ⇒ identical ciphertext ⇒ identical content under one key. True by construction (`Vault__Object_Store.store` L46-L58 computes the id from ciphertext; collisions refuse). Nothing here depends on the author's `content_hash`.

```python
# L81-L85 (deleted)
if path not in merged_map or merged_blob == ours_blob:
    carry_over.append(path)            # stays deleted locally, as in git
else:
    blocked.append(...)
```
- **What:** A locally deleted file the merge does not change stays deleted (it is excluded from `apply_map` by the caller, `Step__Pull__Merge` L98, L128, L234).

```python
# L86-L93 (untracked)
if path not in merged_map:
    continue
local_hash = (local_scan.get(path) or {}).get('content_hash', '')
proven     = blob_hash_fn(merged_blob) if (blob_hash_fn and merged_blob and local_hash) else ''
if proven and proven == local_hash:
    continue
blocked.append((path, 'untracked file would be overwritten by an incoming file'))
```
- **What:** An untracked local file that the merge would create is allowed only when the *decrypted incoming blob* hashes to the same content; otherwise blocked.
- **Why here:** The docstring (L67-L70) names the reason: the tree entry's `content_hash` is the author's claim; trusting it would let a lying commit overwrite an untracked local file silently. This is the one place in the pull path that re-derives a tree claim from the object.
- **Assumes:** `blob_hash_fn` returns `''` when it cannot prove (not-local blob, decrypt failure) ⇒ blocked. Fail-closed.
- **Establishes:** an `untracked` path reaches `apply_map` only if the write is a no-op byte-for-byte.
- **Depended on by:** `_guard_working_tree` L291-L292 raises `Vault__Dirty_Working_Tree_Error` on any `blocked`, before checkout.

**Cross-Function Dependencies:**
- Callers: `Step__Pull__Merge._guard_working_tree` L290.
- Shared state: none.
- Invariant coupling: the "a dirty file is carried over" rule assumes the caller actually removes `carry_over` paths from the write set (it does, L98/L128/L234 of the step) and that `_remove_deleted_flat` (`Vault__Sync__Base.py:L527-L536`) is called with `ours_map`→`merged_map`, so it never deletes an untracked file (untracked paths are not in `ours_map`).
- Tests: `test_Pull__Dirty_Working_Tree.py::test_untracked_file_identical_to_the_incoming_one_is_fine`, `::test_untracked_file_colliding_with_an_incoming_file_is_refused`, `::test_plan_rules`.

**Open Questions:** none.
