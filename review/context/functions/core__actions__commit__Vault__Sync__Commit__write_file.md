## `write_file` / `_write_targets` in sgit_ai/core/actions/commit/Vault__Sync__Commit.py (L211-L330, L332-L352)

**Purpose:** `sgit write <path>`: commit given bytes to HEAD without scanning the working copy, then write the same bytes into the working copy. In slice: the secret guard (`refuse_bytes`), path handling, and the write order.

**Inputs & Assumptions:**
- `path` (str), `content` (bytes), `also` (`{vault_path: bytes}`): user-supplied; paths are checked **first** (`_write_targets`, L219; review N4).
- Requires a write key (L226-L227: `Vault__Read_Only_Error` for a read-only clone).

**Block-by-Block:**

```python
# L332-L352 _write_targets
norm = posixpath.normpath(str(raw or '').replace(os.sep, '/'))
if norm in ('.', '') or str(raw).endswith(('/', os.sep)): raise Vault__Unsafe_Path_Error(...)
dest = guard.safe_join(base, raw)        # no '..', no absolute, no .git/.sg_vault, nothing through an in-tree link
if os.path.isdir(dest): raise ...
targets[norm] = (data, dest)
```
- **Establishes:** every target is a contained, non-structural, non-link, non-directory path, stored normalised.
- Tests: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_a_write_through_an_in_tree_symlinked_folder_is_refused`, `::test_a_write_through_a_symlinked_folder_is_refused`.

```python
# L277-L278
for file_path, file_content in files_to_write.items():
    Vault__Secret_Guard().refuse_bytes(file_path, file_content)
```
- **What:** The zip-with-a-key check on the bytes (`refuse_bytes` L64-L73; no `allowed` escape hatch here, and no hard-link check since no file is read).
- Test: `test_Security__Fixed__Secrets_In_Commits.py::test_write_file_refuses_a_backup_zip`.

```python
# L312-L324
commit_id = vault_commit.create_commit(...)
for file_path, file_content in files_to_write.items():          # the files first, then the ref
    dest = Vault__Path_Guard().safe_join(os.path.abspath(directory), file_path)
    ...open(dest, 'wb').write(file_content)
ref_manager.write_ref(ref_id, commit_id, read_key)
```
- **What:** Commit object stored; working-copy files written (second `safe_join`, so a link planted between L219 and here is refused — the exception then leaves a commit object with no ref pointing at it, which is garbage, not damage); then the clone ref.
- **Why this order:** "a failed write leaves no commit the working copy does not match" (comment L319-L322, review P1).

**Cross-Function Dependencies:** callers `CLI__Vault.cmd_write` (L2570+, not read). Callees as above plus `_load_signing_key`.

**Open Questions:** none.
