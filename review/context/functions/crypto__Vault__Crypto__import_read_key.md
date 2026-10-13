## `import_read_key` in sgit_ai/crypto/Vault__Crypto.py (L223-L234)

```python
# L223-L234
def import_read_key(self, read_key_hex: str, vault_id: str) -> dict:
    read_key_hex          = self.strip_key_prefix(read_key_hex)
    read_key_bytes        = bytes.fromhex(read_key_hex)
    ref_file_id           = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
    branch_index_file_id  = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
    return dict(read_key_bytes=..., read_key=read_key_hex, write_key='', write_key_bytes=None,
                ref_file_id=..., branch_index_file_id=..., vault_id=vault_id)
```

**Purpose:** The read-only clone's counterpart of `derive_keys`: takes a raw read key (never a passphrase) and a vault id, and produces a bundle with no write key. Every read-only path routes through it (`Vault__Sync__Base._derive_keys_for_directory` L313, `Vault__Diff._resolve_keys` L593, `Step__Clone__ReadOnly__Set_Keys.py:L25`, `Vault__Attach.py:L52`, `CLI__Vault.cmd_derive_keys` L2178).

**Inputs & Assumptions:**
- `read_key_hex` (str): bare or prefixed hex. Trust: **untrusted** (argv or `clone_mode.json`).
- `vault_id` (str): Trust: **untrusted**. Not validated here against `VAULT_ID_PATTERN` (compare `parse_vault_key` L130). Used only inside HMAC domains at L226-L227, but the same value is returned at L233 and later used by callers in URLs and paths. What validates it on each path:
  - `clone_mode.json` → `Schema__Clone_Mode.vault_id : Safe_Str__Vault_Id` (`sgit_ai/schemas/Schema__Clone_Mode.py:L14`) when parsed through `Vault__Sync__Base._read_clone_mode` (L290-L292) or `Vault__Diff._read_clone_mode_safe` (L576-L578).
  - `cmd_derive_keys` L2177: regex `[a-z0-9]{4,24}` on the tail.
  - `Vault__Attach.py:L52` and `Step__Clone__ReadOnly__Set_Keys.py:L25`: **nothing found** in this slice; the value arrives as `input.vault_id` / CLI `--vault-id`.
- Precondition: `read_key_hex` is 64 hex characters. `bytes.fromhex` (L225) accepts ANY even-length hex, so 32 or 48 hex digits yield a 16- or 24-byte key that `AESGCM` (L297) accepts as AES-128/192. Length is checked by callers, not here:
  - `clone_mode.json`: `Schema__Clone_Mode.read_key : Safe_Str__Write_Key` (exact 64 lower-hex, `Safe_Str__Write_Key.py:L5-L16`) on the schema path.
  - `CLI__Token_Store.read_key_from_credential` L237-L241: `[0-9a-fA-F]{64}`.
  - `CLI__Vault._resolve_clone_credential` L195: `[0-9a-f]{64}`; `cmd_derive_keys` L2177.
  - `Vault__Attach.py:L52`: **nothing found** in this slice.

**Outputs & Effects:**
- Returns a dict with `write_key=''`, `write_key_bytes=None` (L230-L231) and no `passphrase` key — callers that do `keys['passphrase']` would `KeyError`; `Vault__Components` is built with `keys.get('write_key', '')` (`Vault__Sync__Base.py:L387`).
- Raises `ValueError` from `bytes.fromhex` on non-hex or odd length.
- Pure otherwise.

**Block-by-Block:** L224 strip prefix, L225 decode, L226-L227 derive the two mutable ids exactly as `derive_keys` does (`test_Vault__Crypto__Import_Read_Key.py::test_import_read_key_derived_ids_match_derive_keys`).

**Cross-Function Dependencies:**
- Callees `strip_key_prefix`, `derive_ref_file_id`, `derive_branch_index_file_id` (internal).
- Callers: listed above. `Vault__Sync__Base.py:L313` passes `str(clone_mode.read_key)`, already validated by the schema.
- Invariant coupling: the read-only clone's `clone_mode.json` is itself written by `write_private` (0600) because it holds this key (`Step__Clone__ReadOnly__Setup_Config.py:L42`; TM-R15).
- Tests: `test_Vault__Crypto__Import_Read_Key.py` (6 tests), `test_Vault__Crypto__Key_Prefixes.py::test_import_read_key_accepts_both`, `::test_legacy_read_key_imports`.

**Open Questions:**
- unclear; need to inspect `sgit_ai/core/actions/lifecycle/Vault__Attach.py` and the CLI parser for `--read-key`/`--vault-id` to know whether a short hex read key or an unshaped vault id is refused before reaching L52.
