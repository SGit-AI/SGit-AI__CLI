## `strip_key_prefix` in sgit_ai/crypto/Vault__Crypto.py (L76-L84)

```python
# L76-L84
def strip_key_prefix(self, key: str) -> str:
    key = (key or '').strip()
    for prefix in KEY_PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):]
    return key
```

**Purpose:** The single normalisation point that removes a self-identifying prefix (`sgit_private_vault_`, `sgit_private_read_`, `sgit_public_read_`, legacy `sgit_vk1_`, `sgit_rk1_`; L58-L67) so that key material downstream is byte-identical to the legacy bare form (L42-L46).

**Inputs & Assumptions:**
- `key` (str or None): a credential from argv, a file, `clone_mode.json` or a prompt. Trust: **untrusted**.
- Precondition: none. `None` becomes `''` (L80).

**Outputs & Effects:**
- Returns the stripped, whitespace-trimmed string. Pure; no state.
- Postcondition: at most ONE prefix is removed (L81-L83 returns on first match). A doubly-prefixed string keeps its inner prefix.
- Postcondition: the *declaration* carried by the prefix is discarded; callers that need it must call `classify_key` first (as `read_key_from_credential` does, `CLI__Token_Store.py:L232-L233`).

**Block-by-Block:**

```python
# L80
key = (key or '').strip()
```
- **What:** Tolerates `None` and surrounding whitespace.
- **Depended on by:** `parse_vault_key` (L124) relies on this trim; `format_vault_key`/`format_read_key` (L108, L119) too.

```python
# L81-L84
for prefix in KEY_PREFIXES: ...
```
- **What:** Removes the first matching prefix.
- **Assumes:** no prefix is a prefix of another. Established by inspection of L58-L64: the five values differ at or before the second `_`-separated word.

**Cross-Function Dependencies:**
- No external calls.
- Callers (production): `parse_vault_key` L124, `format_vault_key` L108, `format_read_key` L119, `import_read_key` L224, `CLI__Main.py:L1141,L1169,L1187`, `CLI__Vault.py:L183,L185,L1754,L2173`, `CLI__Token_Store.py:L223,L233`.
- Tests: `tests/unit/crypto/test_Vault__Crypto__Key_Prefixes.py::Test_Prefix_Helpers` (strip of each prefix, no-op on bare, round-trip with format).

**Open Questions:** none.
