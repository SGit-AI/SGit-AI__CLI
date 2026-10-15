## `format_vault_key` in sgit_ai/crypto/Vault__Crypto.py (L105-L109)

```python
# L105-L109
def format_vault_key(self, vault_key: str) -> str:
    vault_key = self.strip_key_prefix(vault_key)
    return f'{VAULT_KEY_PREFIX}{vault_key}'
```

**Purpose:** Produces the on-disk and display form `sgit_private_vault_{passphrase}:{vault_id}`. Every writer of `.sg_vault/local/vault_key` goes through it (`Vault__Sync.py:L123-L125`, `Vault__Bare.py:L45`, `Vault__Attach.py:L74`, `Step__Clone__Setup_Local_Config.py:L36`, `Step__Clone__Headless__Setup_Config.py:L41`, `Step__Move__Build_Temp_Vault.py:L446`).

**Inputs & Assumptions:**
- `vault_key` (str): expected to be a vault key, bare or prefixed. Trust: semi-trusted (comes from init's generator or from the user's argv).
- Precondition: the value IS a vault key. `strip_key_prefix` (L108) removes ANY prefix, including `sgit_private_read_` / `sgit_public_read_`, so a read key passed here is re-labelled `sgit_private_vault_<hex>`. Nothing in this function checks the kind: **nothing found**. Callers listed above all obtain the value from a vault-key path (init generator, `parse_vault_key`-validated input, or the existing `vault_key` file).

**Outputs & Effects:**
- Returns the prefixed string. Pure. Idempotent (`test_Vault__Crypto__Key_Prefixes.py::test_format_vault_key_is_idempotent`); upgrades `sgit_vk1_` (`::test_legacy_is_upgraded_on_reformat`).

**Block-by-Block:** L108 strip, L109 prepend. Nothing else.

**Cross-Function Dependencies:**
- Callee `strip_key_prefix` (internal, L76-L84): removes whitespace and one prefix.
- Callers: listed under Purpose, plus display sites `CLI__Vault.py:L644,L761,L1745`, `Vault__Sync.py:L123`.
- Invariant coupling: readers strip the prefix again via `parse_vault_key` (L124), so the stored material is unchanged (L42-L46 comment; `::test_init_with_explicit_bare_key_stores_prefixed_same_material`).

**Open Questions:** none.
