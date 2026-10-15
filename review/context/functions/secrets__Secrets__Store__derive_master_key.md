## `derive_master_key` in sgit_ai/secrets/Secrets__Store.py (L15-L17)

```python
# L16-L17
salt = f'{SECRETS_SALT_PREFIX}:master'.encode()
return self.crypto.derive_key_from_passphrase(passphrase.encode(), salt)
```

**Purpose:** The credential store's master key: PBKDF2-SHA256 (600k) of the user's passphrase with the FIXED salt `sg-send-secrets-v1:master` (L8).

**Inputs & Assumptions:**
- `passphrase` (str): from `SG_SEND_PASSPHRASE` or `getpass` (`CLI__Credential_Store._prompt_passphrase` L57-L67). Trust: untrusted strength.
- Implicit: the shared PBKDF2 LRU (`Vault__Crypto._pbkdf2_cached`), so the master key AND the passphrase bytes stay cached in the process alongside vault keys (TM-R16).

**Outputs & Effects:** 32 bytes; deterministic across machines for equal passphrases because the salt is constant (TM-R11; `tests/security/test_Security__Known_Gaps.py::test_TM_R11__secrets_store_uses_one_global_salt`, `tests/unit/secrets/test_Secrets__Store.py::test_derive_master_key_is_deterministic`).

**Cross-Function Dependencies:** `Vault__Crypto.derive_key_from_passphrase` (L284-L285). Callers: `store`, `get`, `list_keys`, `delete` (L20, L27, L35, L40) — every operation re-derives (cache makes that cheap).

**Open Questions:** none.
