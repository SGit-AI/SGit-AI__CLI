## `load_private_key_locally` in sgit_ai/crypto/Vault__Key_Manager.py (L63-L67)

```python
# L64-L67
path = os.path.join(local_dir, key_id + '.pem')
with open(path, 'r') as f:
    pem = f.read()
return self.pki.import_private_key_pem(pem)
```

**Purpose:** Loads this clone's signing key before every signed operation: init (`Vault__Sync.py:L91`), commit (`Vault__Sync__Commit._load_signing_key` L24), tag (`Vault__Sync__Tag.py:L116`), pull-merge commits (`Step__Pull__Merge.py:L156,L253`), ignore-apply (`Vault__Ignore__Apply.py:L68`), move sentinels (`Step__Move__Write_Sentinel_Commits.py:L137`).

**Inputs & Assumptions:**
- `key_id` (str): `str(branch_meta.public_key_id)` — from the branch index, which is host-served and read-key-encrypted; validated to `^key-rnd-imm-[0-9a-f]{8,64}$` by `Safe_Str__Key_Id` at schema load (`sgit_ai/safe_types/Safe_Str__Key_Id.py:L5-L15`, `Schema__Branch_Meta.py:L15`). So the path cannot escape `local_dir` on that path.
- `local_dir` (str): `.sg_vault/local`.
- The file: `open('r')` FOLLOWS a symlink at `path` (contrast: writes replace it). A6 could plant a link; what they gain is that sgit reads a PEM of their choosing as the signing key, i.e. the clone signs with a key the attacker chose. **nothing found** here or in the callers that refuses a link at the `.pem` path; threat model TM-F27 mentions `O_NOFOLLOW` reads for the secret scan, not for this read.

**Outputs & Effects:** key object or exception (`FileNotFoundError` when the clone has no key). `Vault__Sync__Commit._load_signing_key` catches `Exception` and proceeds UNSIGNED with a stderr warning (L25-L30; `test_Security__Fixed__Symlinks_And_Local.py::test_an_unsigned_commit_says_so`).

**Cross-Function Dependencies:** Callee `import_private_key_pem` (no passphrase). Callers above. Test: `test_Vault__Key_Manager.py::test_store_and_load_private_key_locally`, `test_Vault__Key_Manager__Permissions.py::test_key_still_loads_after_permission_hardening`.

**Open Questions:**
- unclear; whether `Vault__Sync__Tag.py:L116` and `Step__Pull__Merge.py:L153-L158` also fall back to unsigned on failure, or abort. Not read in this slice.
