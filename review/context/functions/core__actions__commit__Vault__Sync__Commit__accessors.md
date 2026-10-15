## `_load_signing_key` in sgit_ai/core/actions/commit/Vault__Sync__Commit.py (L20-L30)

**Purpose:** This clone's private signing key from `.sg_vault/local/<public_key_id>.pem`, or `None` with a **stderr warning** naming the key id (not the key) — "a commit is never made unsigned silently".

**Inputs & Assumptions:** `branch_meta.public_key_id` (`Safe_Str__Key_Id`); `storage.local_dir(directory)`.

**Outputs & Effects:** key object or `None`; prints to stderr on failure (L26-L29). `load_private_key_locally` (`Vault__Key_Manager.py:L63-L67`) reads the plaintext PEM; no passphrase.

**Cross-Function Dependencies:** callers `commit` L146, `write_file` L307. Test: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_an_unsigned_commit_says_so`.

---

## Not analyzed (out of slice): `_amend_plan` (L185-L209), `_generate_sparse_commit_message` (L354-L372), `_generate_commit_message` (L374-L392).
