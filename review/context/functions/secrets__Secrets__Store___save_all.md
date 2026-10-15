## `_save_all` in sgit_ai/secrets/Secrets__Store.py (L59-L64)

```python
# L60-L64
store_path = str(self.store_path) if self.store_path else self.store_path
plaintext  = json.dumps(secrets, indent=2).encode('utf-8')
encrypted  = self.crypto.encrypt(master_key, plaintext)
from sgit_ai.storage.Vault__Storage import Vault__Storage
Vault__Storage().write_private(store_path, encrypted)    # 0600 even though encrypted
```

**Purpose:** Encrypts the whole store (random IV, `Vault__Crypto.encrypt` L294-L299) and writes it atomically at 0600 (TM-F05 fix).

**Inputs & Assumptions:**
- `store_path`: when `self.store_path` is empty/None, `store_path` is `''`/None and `write_private` → `Vault__Secret_File.write` → `os.path.dirname(None)` raises `TypeError` (or with `''`, writes `./vaults.enc`-less path `''` → `os.replace(tmp, '')` fails). Precondition "store_path is set" is established by `CLI__Credential_Store.setup` L22-L24 on the only production path; **nothing found** inside `Secrets__Store` itself.
- `secrets` (dict): the code's own structure.

**Outputs & Effects:** file replaced; ciphertext length reveals the JSON length (TM-R08 analogue). Each save uses a fresh IV, so repeated saves of identical content differ.

**Cross-Function Dependencies:** `encrypt` (internal), `Vault__Storage.write_private` (`sgit_ai/storage/Vault__Storage.py:L128-L131`) → `Vault__Secret_File.write`. The import of `Vault__Storage` inside a `crypto`-adjacent module is local (L63) to respect the "storage must not be imported by crypto" layering noted in `Vault__Secret_File.py:L3-L5`. Callers: `store` L24, `delete` L45. Test: `test_Secrets__Store.py::test_file_is_encrypted`, `::test_creates_parent_directory`.

**Open Questions:** none.
