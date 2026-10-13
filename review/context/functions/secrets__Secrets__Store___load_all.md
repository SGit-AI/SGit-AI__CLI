## `_load_all` in sgit_ai/secrets/Secrets__Store.py (L48-L57)

```python
# L49-L57
store_path = str(self.store_path) if self.store_path else self.store_path
if not store_path or not os.path.isfile(store_path):
    return {}
with open(store_path, 'rb') as f:
    encrypted = f.read()
if not encrypted:
    return {}
plaintext = self.crypto.decrypt(master_key, encrypted)
return json.loads(plaintext.decode('utf-8'))
```

**Purpose:** Decrypts the whole store into a dict.

**Inputs & Assumptions:**
- `master_key` (bytes): from `derive_master_key`.
- The file at `store_path`: written by `_save_all`; 0600 (`tests/unit/sync/test_Vault__Sync__File_Modes.py::test_secrets_store_is_0600`). Trust: local, same user. `open('rb')` follows a symlink at the path (writes do not).
- A missing or EMPTY file is an empty store (L50-L55; `test_Secrets__Store__Edge_Cases.py::test_empty_store_file_returns_empty_line_55`, `::test_no_store_path__load_returns_empty`). So deleting or truncating `vaults.enc` silently yields "no stored vaults" rather than an error — and the next `store` call will create a fresh store under whatever passphrase is supplied.

**Outputs & Effects:** dict; raises `InvalidTag` on wrong passphrase or tampering, `json`/`UnicodeDecodeError` if the authenticated plaintext is malformed (only a master-key holder could cause that).

**Cross-Function Dependencies:** `Vault__Crypto.decrypt` (L301-L305, no AAD). Callers: `store`, `get`, `list_keys`, `delete`.

**Open Questions:** none.
