## `format_read_key` in sgit_ai/crypto/Vault__Crypto.py (L111-L121)

```python
# L119-L121
read_key_hex = self.strip_key_prefix(str(read_key_hex or ''))
prefix       = READ_KEY_PUBLIC_PREFIX if public else READ_KEY_PREFIX
return f'{prefix}{read_key_hex}'
```

**Purpose:** Display form of a read key, declared private (`sgit_private_read_`) or deliberately public (`sgit_public_read_`, L114-L117). The declaration is what secret scanners key on (L48-L56).

**Inputs & Assumptions:**
- `read_key_hex` (str or anything `str()`-able): Trust: semi-trusted (derived hex from `derive_keys`, or the `read_key` field of `clone_mode.json` at `CLI__Vault.py:L1706,L1725`).
- `public` (bool): the caller's declaration. Trust: trusted (only `Vault__Publish.py:L77` passes `True`).
- Precondition: the value is a read key. As with `format_vault_key`, `strip_key_prefix` (L119) removes any prefix including `sgit_private_vault_`, so a vault key passed here is re-labelled as a read key. Nothing here checks: **nothing found**. All production callers pass `keys['read_key']` / `c.read_key.hex()` / `clone_mode['read_key']`.

**Outputs & Effects:**
- Returns the prefixed string. Pure.
- Postcondition: calling it on an already-declared key REPLACES the declaration with the `public` argument (`tests/unit/crypto/test_Vault__Crypto__Key_Prefixes.py::Test_Public_Read_Key_Formatting::test_reformatting_can_flip_the_declaration`). The material is unchanged (`::test_public_and_private_read_keys_are_the_same_material`).

**Cross-Function Dependencies:**
- Callee `strip_key_prefix` (internal).
- Callers: `CLI__Create.py:L102`, `CLI__Vault.py:L313,L1725,L1769`, `Vault__Publish.py:L77` (public=True, used as a file NAME in the published layout).

**Open Questions:** none.
