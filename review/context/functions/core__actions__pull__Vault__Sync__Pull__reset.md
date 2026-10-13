## `reset` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L16-L70)

**Purpose:** Moves this clone's **clone-branch** ref to `commit_id` and rewrites the working copy to that commit's tree (`sgit history reset`). It is a local-only operation on the clone's own branch; it never touches the named ref or a baseline.

**Inputs & Assumptions:**
- `directory` (str): trusted.
- `commit_id` (str | None): user-supplied revision (`HEAD~2`, `@{1}`, a tag, a short id) resolved by `Vault__Revision.resolve_soft` (L44-L45); `None` ⇒ the current head (L39-L42). Trust: user input; the resolved id must be a local object (L49-L53 raise otherwise).
- Implicit: local config (`my_branch_id`, L26-L27), the local index (L29-L35), the clone ref (L37).

**Outputs & Effects:**
- **Working-copy writes:** `_checkout_flat_map` (L60) then `_remove_deleted_flat` (L61) — every path goes through `Vault__Path_Guard` (`Vault__Sync__Base.py:L511-L518`, L531).
- **Ref write:** the clone branch's `head_ref_id` ← `commit_id` (L63) *after* the checkout.
- No network call. No signature check: the target is already a local object (it was accepted when it arrived).
- Raises `RuntimeError` for missing index/branch/commit (L31, L35, L41, L52-L53).

**Block-by-Block:**

```python
# L26-L37
local_config = self._read_local_config(directory, storage)
branch_id    = str(local_config.my_branch_id)
...
branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
...
current_commit_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)
```
- **What:** Resolve this clone's branch and its current head.
- **Assumes:** `my_branch_id` is set (a read-only clone has `None` → `'None'` → "Branch not found"; the CLI gates reset with `_check_read_only` elsewhere — not traced).

```python
# L47-L61
target_commit = vault_commit.load_commit(commit_id, read_key)   # FileNotFoundError → RuntimeError
target_flat   = sub_tree.flatten(str(target_commit.tree_id), read_key)
disk_map      = self._scan_local_directory(directory)
self._checkout_flat_map(directory, target_flat, obj_store, read_key)
self._remove_deleted_flat(directory, disk_map, target_flat)
```
- **What:** Flatten the target tree, scan disk, write every target file, delete what is on disk but not in the target.
- **Why here:** No dirty-tree guard — `reset` is defined to discard working-copy state (unlike pull). `disk_map` is the deletion baseline, so **untracked files are deleted too** (anything on disk not in `target_flat`; `_scan_local_directory` honours `.gitignore` so ignored files survive, L411 of Base).
- **Assumes:** `Vault__Object_Store.load` raises `Vault__Object_Missing_Error` (a `FileNotFoundError` subclass? — `_checkout_flat_map` swallows *every* exception per file, L524-L525 of Base, so a missing blob leaves that file unwritten silently; `_remove_deleted_flat` then does not delete it either since it is in `target_flat`). So a reset onto a commit whose blobs are not all local leaves stale content for those paths with no error.
- **Establishes:** disk ≈ target tree, modulo unfetched blobs.

```python
# L63
ref_manager.write_ref(str(branch_meta.head_ref_id), commit_id, read_key)
```
- **What:** Move the clone ref (and append to the reflog, `Vault__Ref_Manager.write_ref` L19-L24).
- **Why here:** after the checkout, so a failed checkout leaves the ref unmoved.

**Cross-Function Dependencies:**
- Callee `Vault__Revision.resolve_soft` (internal, not read): resolves user syntax; see Open Questions.
- Callee `Vault__Sync__Base._checkout_flat_map` (L503-L525): per-file `is_protected` → `safe_join` → decrypt → write; all exceptions swallowed per file.
- Callee `_remove_deleted_flat` (L527-L536): `is_writable` guard, `os.remove` of regular files, then `_remove_empty_dirs`.
- Callers: `CLI__Vault.cmd_reset` (L1089, not read in detail); `cmd_undo`.
- Shared state: clone ref, working copy, reflog.
- Invariant coupling: this is one of the writers of a **clone** ref; the verify-then-accept rule is about **named** refs and baselines, which this never writes.

**Open Questions:**
- unclear; whether `resolve_soft` can return an id that is not `Safe_Str__Object_Id`-shaped (it is used in `load_commit` → `object_path` join). `Vault__Object_Store.resolve_id` (L99-L120, not read) is the likely normaliser.
