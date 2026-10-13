## `derive_keys_from_vault_key` in sgit_ai/crypto/Vault__Crypto.py (L219-L221)

```python
# L219-L221
def derive_keys_from_vault_key(self, vault_key: str) -> dict:
    passphrase, vault_id = self.parse_vault_key(vault_key)
    return self.derive_keys(passphrase, vault_id)
```

**Purpose:** The entry point almost every command uses to turn the stored or supplied vault key into the key bundle (about 40 call sites across `sgit_ai/cli`, `core`, `workflow`; e.g. `Vault__Sync__Base.py:L50`, `Vault__Sync.py:L57`, `CLI__Token_Store.py:L220,L236,L242`).

**Inputs & Assumptions:**
- `vault_key` (str): bare or prefixed. Trust: **untrusted** (argv, `vault_key` file, backup zip, env).
- Precondition: none; `parse_vault_key` validates shape and raises `ValueError` otherwise.

**Outputs & Effects:**
- Returns the `derive_keys` dict (including `passphrase`). Raises `ValueError` for malformed input (propagated from L127/L131).
- Two PBKDF2 runs on a cold cache.

**Block-by-Block:** parse (L220) then derive (L221). Nothing else.

**Cross-Function Dependencies:**
- Callee `parse_vault_key` (internal, L123-L136): the only validation on this path. Callee `derive_keys` (internal, L205-L217).
- Callers assume this is where a bad vault id is refused; none re-check (`CLI__Vault.py:L1297` uses `.get('vault_id')` on the result).
- Invariant coupling: a read key in `{64-hex}:{vault_id}` form passed here is treated as a passphrase and derives a wrong-but-valid key bundle (the "No branch index found" symptom described at `CLI__Vault.py:L194-L198`). Callers that accept both forms must route first: `CLI__Vault._resolve_clone_credential` (L160-L200), `CLI__Token_Store.read_key_from_credential` (L226-L242), `CLI__Vault.cmd_derive_keys` (L2176-L2186). `CLI__Token_Store.resolve_read_key` L219 deliberately does not (a `vault_key` file is "a vault key by definition").
- Tests: `test_Vault__Crypto__Key_Prefixes.py::test_derived_keys_identical_for_both_forms`, `test_Vault__Crypto.py::test_vector_1__derive_keys_from_vault_key`.

**Open Questions:** none.
