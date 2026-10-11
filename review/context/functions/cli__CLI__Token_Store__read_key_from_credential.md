## `read_key_from_credential` in sgit_ai/cli/CLI__Token_Store.py (L226-L242)

```python
# L230-L242
crypto = Vault__Crypto()
raw    = (raw or '').strip()
kind   = crypto.classify_key(raw)
body   = crypto.strip_key_prefix(raw)
head   = body.partition(':')[0]
if kind == Enum__Key_Kind.VAULT:
    return crypto.derive_keys_from_vault_key(body)['read_key_bytes']
is_read_shape = bool(re.fullmatch(r'[0-9a-fA-F]{64}', head))
if kind in (Enum__Key_Kind.READ_PRIVATE, Enum__Key_Kind.READ_PUBLIC) or is_read_shape:
    if not is_read_shape:
        raise ValueError('this declares a read key, but it does not start with 64 hex characters')
    return bytes.fromhex(head)
return crypto.derive_keys_from_vault_key(body)['read_key_bytes']
```

**Purpose:** Turn any credential string into read-key bytes following the declaration-first rule (`CLI__Vault.py:L160-L176`): a declared VAULT key is never mistaken for the shorthand even if its passphrase is 64 hex; a declared READ key must be 64 hex; a bare string is routed by shape.

**Inputs & Assumptions:**
- `raw` (str): argv or a re-prefixed `clone_mode` value. Trust: **untrusted**.
- Routing facts:
  - `VAULT` → `derive_keys_from_vault_key` → `parse_vault_key` validates `{passphrase}:{vault_id}`; `ValueError` otherwise.
  - Declared read or 64-hex head → `bytes.fromhex(head)` (32 bytes); the tail after `:` (a vault id, if present) is IGNORED — a read key alone cannot derive file ids, which this caller does not need (callers only decrypt local objects).
  - `UNKNOWN` and not 64-hex → treated as a bare vault key.
- The hex test accepts UPPERCASE (`[0-9a-fA-F]`, L237) whereas `CLI__Vault._resolve_clone_credential` L195 and `cmd_derive_keys` L2177 accept lowercase only; `Safe_Str__Write_Key` lower-cases before matching (`to_lower_case = True`). An upper-case 64-hex head is therefore a read key here and a passphrase at clone. Two rules recorded; neither cited as wrong.

**Outputs & Effects:** 32 bytes or `ValueError`; PBKDF2 on the vault paths. Pure.

**Cross-Function Dependencies:** `classify_key` (L86-L103), `strip_key_prefix` (L76-L84), `derive_keys_from_vault_key` (L219-L221). Callers: `resolve_read_key` L215, L223. Tests: `test_CLI__Token_Store.py::test_resolve_read_key_from_vault_key_arg`; the clone-side equivalents in `test_Vault__Crypto__Key_Prefixes.py::Test_Clone_Credential_Routing`.

**Open Questions:**
- unclear; whether a dedicated unit test covers the "declared read key that is not 64 hex → ValueError" branch (L239-L240) for THIS function (the clone-side `::test_read_prefix_without_vault_id_is_a_clear_error` covers `CLI__Vault`).
