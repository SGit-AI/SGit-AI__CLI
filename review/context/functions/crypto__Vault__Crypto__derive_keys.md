## `derive_keys` in sgit_ai/crypto/Vault__Crypto.py (L205-L217)

```python
# L205-L217
def derive_keys(self, passphrase: str, vault_id: str) -> dict:
    read_key_bytes        = self.derive_read_key(passphrase, vault_id)
    write_key_bytes       = self.derive_write_key(passphrase, vault_id)
    ref_file_id           = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
    branch_index_file_id  = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
    return dict(read_key_bytes=..., read_key=read_key_bytes.hex(), write_key_bytes=..., write_key=write_key_bytes.hex(),
                ref_file_id=..., branch_index_file_id=..., passphrase=passphrase, vault_id=vault_id)
```

**Purpose:** The full-capability key bundle: read key (AES), write key (bearer header the host checks, threat model §1), and the two HMAC-derived mutable file ids. This dict is what a full clone carries in memory for the life of a command (`Vault__Components`, `sgit_ai/core/Vault__Components.py:L14-L19`).

**Inputs & Assumptions:**
- `passphrase` (str), `vault_id` (str): Trust: semi-trusted; on the main path both come from `parse_vault_key` (L220), which validated `vault_id` only. Called directly by nothing else in `sgit_ai/` (grep: only L221).
- Implicit: the PBKDF2 LRU cache (see `_pbkdf2_cached`).

**Outputs & Effects:**
- Returns a plain `dict` holding raw key bytes, hex forms AND the passphrase (L216). No Type_Safe wrapper (CLAUDE.md rule 1 is not applied to this return value; `Vault__Components` then holds `read_key : bytes` with a comment "no Safe_Bytes primitive", `Vault__Components.py:L16`).
- Cost: two PBKDF2 runs on a cold cache.
- No state writes other than the cache.

**Block-by-Block:**

```python
# L206-L207
read_key_bytes  = self.derive_read_key(passphrase, vault_id)
write_key_bytes = self.derive_write_key(passphrase, vault_id)
```
- **What:** Two independent PBKDF2 derivations with different salt prefixes (L19, L34).
- **Establishes:** read key and write key are not derivable from each other (threat model §1; `test_Vault__Crypto.py::test_read_key_and_write_key_are_independent`).
- **Depended on by:** every encrypt/decrypt and every `x-sgraph-vault-write-key` header (`Vault__API.py:L95,L104,L121`).

```python
# L208-L209
ref_file_id / branch_index_file_id
```
- **What:** `HMAC(read_key, domain:vault_id)[:12]` with fixed wire prefixes.
- **Assumes:** only the read key is needed to locate refs and index — by design, so read-only clones can find them (`import_read_key` L226-L227 computes the same values; `test_Vault__Crypto__Import_Read_Key.py::test_import_read_key_derived_ids_match_derive_keys`).

**Cross-Function Dependencies:**
- Callees `derive_read_key`, `derive_write_key`, `derive_ref_file_id`, `derive_branch_index_file_id` (internal; see accessors record).
- Callers: `derive_keys_from_vault_key` (L221) only.
- Shared state: the returned dict is stored by `Vault__Sync__Base._init_components` into `Vault__Components` (`Vault__Sync__Base.py:L384-L396`); `write_key` becomes `Safe_Str__Write_Key` there (64-hex MATCH, `sgit_ai/safe_types/Safe_Str__Write_Key.py:L5-L16`).
- Vectors: `test_Vault__Crypto.py::test_vector_1__derive_keys_all_at_once`, `::test_vector_2__derive_keys_from_vault_key`.

**Open Questions:** none.
