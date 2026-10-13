## `store` in sgit_ai/secrets/Secrets__Store.py (L19-L24)

```python
# L20-L24
master_key = self.derive_master_key(passphrase)
secrets    = self._load_all(master_key)
secrets[key] = dict(value=value, created_at=int(Timestamp_Now()))
self._save_all(master_key, secrets)
```

**Purpose:** Adds or replaces one alias → vault-key entry in the encrypted store (`sgit vault add`).

**Inputs & Assumptions:**
- `passphrase` (str): must be the one the store was created with — `_load_all` fails with `InvalidTag` otherwise (`test_Secrets__Store.py::test_wrong_passphrase_fails`). On a NEW store (no file) any passphrase works and becomes the store's passphrase.
- `key` (str): alias, any string (`test_Secrets__Store__Edge_Cases.py::test_store__special_characters_in_key`); becomes a JSON key.
- `value` (str): the vault key in plaintext form (`CLI__Vault.cmd_vault_add` L1660-L1661).
- Implicit: `self.store_path`.

**Outputs & Effects:**
- Whole-store read-modify-write; the file is rewritten via `_save_all` → `write_private` (0600, atomic). Two concurrent `store` calls are not serialised (no lock): the second rename wins and the first entry is lost. **nothing found** that prevents it; single-user CLI usage is the implicit assumption.
- `created_at` from `Timestamp_Now`.

**Cross-Function Dependencies:** `derive_master_key`, `_load_all`, `_save_all` (internal). Caller: `CLI__Credential_Store.add_vault` L29. Tests: `test_Secrets__Store.py::test_store_and_get`, `::test_overwrite_existing_key`, `test_Secrets__Store__Edge_Cases.py::test_store__overwrite_preserves_other_keys`.

**Open Questions:** none.
