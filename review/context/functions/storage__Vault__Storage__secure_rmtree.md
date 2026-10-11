## `secure_rmtree` in sgit_ai/storage/Vault__Storage.py (L165-L184)

```python
# L167-L184
if not os.path.isdir(directory): return 0
count = 0
for root, dirs, files in os.walk(directory, topdown=False):
    for fname in files:
        self.secure_unlink(os.path.join(root, fname)); count += 1
    for dname in dirs:
        try: os.rmdir(os.path.join(root, dname))
        except OSError: pass
try: os.rmdir(directory)
except OSError: pass
return count
```

**Purpose:** Wipe every file under `.sg_vault` for `sgit vault rekey` (`Vault__Sync__Lifecycle.rekey_wipe` L59-L61), then remove the folders.

**Inputs & Assumptions:** `directory` = `storage.sg_vault_dir(directory)` (trusted). `os.walk` with default `followlinks=False` does not descend into a symlinked directory; such a directory appears in `dirs`, and `os.rmdir` on a symlink fails with `ENOTDIR`/`EINVAL` and is swallowed (L178-L179), so a link-dir inside `.sg_vault` survives the wipe and the final `rmdir(directory)` then fails silently (L181-L183). `count` counts attempted unlinks, not successes (`secure_unlink` swallows errors).

**Outputs & Effects:** Deletes; returns the number of files visited. `isdir(directory)` follows a link: if `.sg_vault` itself is a symlink, the walk wipes the **target** tree.

**Cross-Function Dependencies:** Callee `secure_unlink` L146. Caller `Vault__Sync__Lifecycle.rekey_wipe` L61 (then `clear_kdf_cache`, `rekey_init`). Tests: `tests/unit/sync/test_Vault__Sync__Secure_Unlink.py::Test_Vault__Storage__Secure_Rmtree`, `::Test_Vault__Sync__Rekey_Wipe__Secure`.

**Open Questions:**
- `.sg_vault` as a symlink to another vault's store (A6 or a user mistake) → that store is zeroed. Nothing checks `islink(directory)`.
- Contrast with `Vault__Sync__Lifecycle.uninit` L123 which uses `shutil.rmtree(sg_dir)` (no zeroing) after writing a backup that contains the plaintext key; the two removal paths differ in what they promise.
