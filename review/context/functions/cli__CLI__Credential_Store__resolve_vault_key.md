## `resolve_vault_key` in sgit_ai/cli/CLI__Credential_Store.py (L47-L55)

```python
# L48-L55
if ':' in alias_or_key:
    return alias_or_key
if not passphrase:
    passphrase = self._prompt_passphrase()
vault_key = self.get_vault_key(passphrase, alias_or_key)
if not vault_key:
    raise RuntimeError(f'No vault key found for alias "{alias_or_key}"')
return vault_key
```

**Purpose:** Accept either a literal vault key (anything containing `:`) or an alias to look up in the store. **No production caller**: grep over `sgit_ai/` finds only the definition (`Vault__Restore._resolve_vault_key` is a different method). Exercised by `tests/unit/cli/test_CLI__Credential_Store.py::test_resolve_vault_key__*`.

**Inputs & Assumptions:** `alias_or_key` (str): the `:` test means an alias can never contain a colon and a prefixed key (`sgit_private_vault_x:y`) is treated as a key without stripping. `passphrase` (str or None): prompt/env fallback.

**Outputs & Effects:** returns the key or raises `RuntimeError`; triggers auto-lock check and activity touch via `get_vault_key`.

**Cross-Function Dependencies:** `_prompt_passphrase` (L57-L67), `get_vault_key` (L32-L36).

**Open Questions:** none.
