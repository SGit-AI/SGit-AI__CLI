## `secure_unlink` in sgit_ai/storage/Vault__Storage.py (L146-L163)

```python
# L148-L163
if os.path.islink(path):
    try: os.unlink(path)
    except OSError: pass
    return
try:
    size = os.path.getsize(path)
    with open(path, 'r+b') as fh:
        if size > 0:
            fh.write(b'\x00' * size); fh.flush(); os.fsync(fh.fileno())
    os.unlink(path)
except OSError:
    pass
```

**Purpose:** Zero-overwrite + fsync + unlink, to shorten the window in which key material is recoverable from disk after `rekey_wipe` (docstring L147).

**Inputs & Assumptions:**
- `path` (str): from an `os.walk` of `.sg_vault` (via `secure_rmtree`) or a test. Trust: filesystem-derived within the vault's own folder.
- Implicit: that an in-place overwrite reaches the same physical blocks. On copy-on-write or journaling filesystems, SSDs with wear-levelling, or snapshots, it does not — `nothing found` that documents this limit in the threat model §5 table (the `secure_*` names promise more than the function can establish; recorded, not judged).
- `b'\x00' * size` allocates the whole file size in memory (L158) — a multi-GB object in `bare/data` would be materialised as one bytes object; `tests/unit/sync/test_Vault__Sync__Secure_Unlink.py::test_secure_unlink_multi_mb_file` covers MB scale only.

**Outputs & Effects:** Overwrites then unlinks; all `OSError`s swallowed (L162-L163) so a failed wipe is silent. Links are unlinked without touching the target (L148-L153; `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_secure_unlink_of_a_link_never_zeroes_its_target`).

**Block-by-Block:**
- L148-L153: link guard. `islink` then `unlink` — a swap between the two is a plain unlink of whatever is there; no overwrite of a target can result because `open(..., 'r+b')` is never reached on this branch.
- L155-L156: `getsize` then `open('r+b')` — `open` follows a link if one was swapped in after L148 (TOCTOU, same shape as `safe_join`'s); the target would be zeroed. `nothing found` that opens with `O_NOFOLLOW` here (contrast `read_regular`).

**Cross-Function Dependencies:** Caller `secure_rmtree` L173 only. Tests: `tests/unit/sync/test_Vault__Sync__Secure_Unlink.py::Test_Vault__Storage__Secure_Unlink`.

**Open Questions:**
- The link-swap window between L148 and L156 (A6 on the same machine during `rekey_wipe`).
