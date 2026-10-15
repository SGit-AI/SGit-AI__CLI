## `parse_vault_key` in sgit_ai/crypto/Vault__Crypto.py (L123-L136)

```python
# L123-L136
def parse_vault_key(self, vault_key: str) -> tuple:
    vault_key = self.strip_key_prefix(vault_key)
    parts = vault_key.rsplit(':', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f'Invalid vault key format: expected {{passphrase}}:{{vault_id}}')
    passphrase = parts[0]
    vault_id   = parts[1]
    if not VAULT_ID_PATTERN.match(vault_id):
        raise ValueError(f'Invalid vault_id "{vault_id}": must be 4-24 lowercase alphanumeric characters ...')
    return passphrase, vault_id
```

**Purpose:** Splits `{passphrase}:{vault_id}` and is the only place the vault id's shape is enforced (`VAULT_ID_PATTERN = ^[a-z0-9]{4,24}$`, L24). The vault id becomes a path segment on the host (L21-L23 comment) and the suffix of every KDF salt (L139, L143).

**Inputs & Assumptions:**
- `vault_key` (str): Trust: **untrusted** (argv, env, file, backup zip).
- Precondition: none.

**Outputs & Effects:**
- Returns `(passphrase, vault_id)`.
- Raises `ValueError` on no colon, empty half, or a vault id outside the pattern. The second message echoes the rejected `vault_id` (L132) but never the passphrase.
- Postcondition: `vault_id` matches the pattern; `passphrase` is any non-empty string, including one containing `:` (L125 `rsplit(':', 1)`; `tests/unit/crypto/test_Vault__Crypto.py::test_parse_vault_key__passphrase_with_colons`). Passphrase strength is not examined here or anywhere else in the slice (TM-R16).

**Block-by-Block:**

```python
# L124-L125
vault_key = self.strip_key_prefix(vault_key)
parts = vault_key.rsplit(':', 1)
```
- **What:** Normalise, then split at the LAST colon.
- **Why here:** Lets passphrases contain colons; makes the vault id the unambiguous tail.
- **Depended on by:** L126-L135.

```python
# L126-L127, L130-L135
if len(parts) != 2 or not parts[0] or not parts[1]: raise ...
if not VAULT_ID_PATTERN.match(vault_id): raise ...
```
- **What:** Shape checks.
- **Establishes:** the vault id is safe for S3 paths and salts; the id cannot contain `/`, `..`, `-`, upper case or spaces.
- **Depended on by:** every `derive_*` using `vault_id` in a salt or domain; every caller that puts `vault_id` in a URL (`Vault__API.py:L93,L99,L103`).

**Cross-Function Dependencies:**
- Callee `strip_key_prefix` (internal).
- Callers: `derive_keys_from_vault_key` (L220), `CLI__Vault.cmd_info` (L1744, to print identity before PBKDF2).
- Note that `import_read_key` (L223-L234) does NOT run this check on its `vault_id`; see that record.
- Tests: `test_Vault__Crypto.py::Test_Vault__Crypto__Vault_Key_Derivation` (simple, colons, no colon, empty halves, bad pattern); `test_Vault__Crypto__Key_Prefixes.py::test_parse_vault_key_accepts_both`, `::test_invalid_key_still_rejected`.

**Open Questions:** none.
