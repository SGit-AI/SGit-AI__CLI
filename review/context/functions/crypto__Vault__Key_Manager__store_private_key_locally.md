## `store_private_key_locally` in sgit_ai/crypto/Vault__Key_Manager.py (L56-L61)

```python
# L57-L61
import stat
pem  = self.pki.export_private_key_pem(private_key)
path = os.path.join(local_dir, key_id + '.pem')
from sgit_ai.crypto.Vault__Secret_File import Vault__Secret_File
Vault__Secret_File().write(path, pem)                  # 0600, never through a link
```

**Purpose:** Persists THIS clone's signing key to `.sg_vault/local/<key_id>.pem`, the asset the threat model lists as "Clone signing keys (private) — everyone but that clone" (§2). Written once per clone branch (`Vault__Branch_Manager.create_clone_branch` L65).

**Inputs & Assumptions:**
- `key_id` (str): generated id (L58 of Branch_Manager). Joined into a path with no shape check here.
- `private_key`: freshly generated EC key.
- `local_dir` (str): `storage.local_dir(directory)` → `<dir>/.sg_vault/local` (`Vault__Storage.py:L30-L31`).
- Precondition: `local_dir` is not itself a symlink to somewhere hostile. `Vault__Secret_File.write` refuses to write THROUGH a link at `path` but creates its temp file inside whatever `os.path.dirname(path)` resolves to (L18-L22 there). **nothing found** in this slice checking the parent; threat model §5 "Symlinks" says links above the vault root are allowed.

**Outputs & Effects:**
- The PEM is written UNENCRYPTED (no passphrase at L58 → `NoEncryption`, `PKI__Crypto.py:L38-L39`), protected by mode 0600 only (`tests/unit/crypto/test_Vault__Key_Manager__Permissions.py::test_private_key_pem_is_0600_even_under_permissive_umask`, `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_uninit_then_restore_keeps_signing_and_the_key_private`).
- `import stat` (L57) is unused — a leftover from the chmod-after-write version the threat model's TM-F16 row says was replaced.

**Block-by-Block:** L58 export, L59 path, L60-L61 atomic 0600 write.

**Cross-Function Dependencies:**
- Callees: `export_private_key_pem` (`PKI__Crypto.py:L36-L44`), `Vault__Secret_File.write` (`sgit_ai/crypto/Vault__Secret_File.py:L14-L35`).
- Callers: `Vault__Branch_Manager.create_clone_branch` L65 only. Backups carry the file (`Vault__Sync__Lifecycle.py:L173` restores `local/*.pem` via `write_private`).
- Read back by `load_private_key_locally`.

**Open Questions:** none.
