# F08 — `write_file` Surgical Path: Encryption Equivalence

**Severity:** LOW (no leak found)
**Class:** Code-path equivalence / regression-risk
**Disposition:** OK + TEST GAP
**Files:** `sgit_ai/sync/Vault__Sync.py:227-340`,
`sgit_ai/sync/Vault__Sub_Tree.py:115-188` (`build_from_flat`),
`tests/unit/sync/test_Vault__Sync__Write_File.py`

## 1. Path Comparison

### Standard `commit` path (full scan)
- Walks working dir
- For each file: `crypto.encrypt(read_key, content)` → blob, store, dedupe
- `Vault__Sub_Tree.build(...)` → uses `encrypt_metadata_deterministic` and
  `encrypt_deterministic` for tree nodes

### `write_file` path (surgical)
- Loads HEAD's flat map via `sub_tree.flatten`
- Re-uses existing `blob_id` if `content_hash` matches (line 278-280)
- Otherwise: `crypto.encrypt(read_key, file_content)` → blob, store
  (line 282-284) — **identical primitive**
- Calls `sub_tree.build_from_flat(flat, read_key)` which uses the **same**
  `encrypt_metadata_deterministic` calls as `build` (verified by reading
  Vault__Sub_Tree.py:154-161)

**Cryptographic primitives are identical.** No skipped encryption; no
plaintext leak.

## 2. Read-Only Guard on Share Clones

`write_file` calls `_init_components(directory)` which loads `c.write_key`.
If absent, downstream commit ops fail. Verified by checking
`test_delete_on_remote_read_only_raises`: the same `_init_components` flow
is used.

**Concern:** `write_file` does not explicitly check `c.write_key` before
mutating `flat`. It relies on the commit step to fail. If a future bug
allowed commit to proceed without a write_key, write_file would silently
succeed locally (no server push). **Defensive guard recommended:**

```python
if not c.write_key:
    raise RuntimeError('write_file requires write access')
```

at the top of `write_file`, mirroring `delete_on_remote`.

## 3. Validation Skips

The plan asked: "does write_file skip gitignore / large-blob / hooks?"

- **gitignore:** `write_file` operates on a single explicit path; gitignore
  is irrelevant for the surgical path (the user said "write this file").
  However, if the user calls `write_file(path='secret.env')` and `secret.env`
  is in `.sgignore`, the file IS committed to the vault. **This is by design**
  for the agent use case; document explicitly.
- **Large-blob threshold:** the code uses `is_large = len(encrypted) >
  LARGE_BLOB_THRESHOLD` (line 284). Same threshold as `commit`. ✓
- **Hooks (pre-commit etc.):** None exist in this codebase. N/A.

## 4. content_hash_enc Stale-Ciphertext Check

If existing blob with same `content_hash` exists, `write_file` re-uses
`old_entry['blob_id']` (line 279). Then `flat[file_path] = dict(...
content_hash=file_hash, ...)` (line 289-293) — uses the **freshly computed**
file_hash. So `content_hash_enc` in the resulting tree is consistent with
the actual content. **No stale-ciphertext bug.**

The blob_id reuse is safe because blob_id is `obj-cas-imm-{sha256(ct)[:12]}`,
i.e., the ciphertext hash. Two encrypts of the same plaintext under the same
key with **random IVs** produce different ciphertexts and different blob_ids
— so the dedup is keyed on plaintext content_hash, not blob_id. The first
write wins; subsequent identical writes just point at the same blob.

## 5. Working-Dir Sync

After commit, lines 325-340 write the new content to the working directory
under `os.path.join(directory, file_path)`, with `os.makedirs(parent,
exist_ok=True)`. **Plaintext on disk is intentional** — that's the working
copy. Equivalent to `git checkout`.

## 6. The "unchanged" Path: No New Commit

If `not any_changed and not new_paths and parent_id`, return `unchanged=True`
without creating a new commit (lines 296-303). **No tree mutation, no
encryption, no leak.** Verified safe.

## 7. Test Coverage (positive cases excellent; security gaps)

`test_Vault__Sync__Write_File.py` covers:
- Create new file ✓
- Disk content matches ✓
- Nested path ✓
- ls integration ✓
- Same content → unchanged ✓
- Different content → new commit ✓
- Custom + auto message ✓
- Atomic multi-file via `also` ✓
- Single-commit semantics ✓
- No-scan property ✓

**Gaps:**
- **No "blob is encrypted" test.** Mutation M7 (replace `encrypt(read_key,
  file_content)` with `file_content` — identity) would produce a passing test
  for `test_written_file_appears_on_disk` (the working dir is plaintext
  anyway) and a passing test for `test_write_file_creates_new_file`
  (blob_id pattern is matched). The mutation would only be caught by
  asserting that `bare/data/{blob_id}` content is NOT equal to the plaintext.
  **High-priority test to add.**
- No test verifies that `write_file` on a read-only clone raises.
- No test verifies `name_enc` / `size_enc` / `content_hash_enc` / `content_type_enc`
  are present on the new tree entry (i.e., none are silently dropped).

## 8. Disposition

- **No code change required**, but:
- **One small defensive guard** (read-only check at top of `write_file`).
- **Three security tests** to add (Mutation M7 + two consistency tests).
- **No redesign needed.**
