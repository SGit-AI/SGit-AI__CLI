## `compute_object_id` in sgit_ai/crypto/Vault__Crypto.py (L183-L190)

```python
# L187-L190
if hex_len not in (12, 32):
    raise ValueError(...)
raw_hash = hashlib.sha256(ciphertext).hexdigest()[:hex_len]
return f'obj-cas-imm-{raw_hash}'
```

**Purpose:** Content address of a ciphertext: `obj-cas-imm-` + SHA-256 hex truncated to 12 (format 1, 48 bits) or 32 (format 2, 128 bits) characters. This is what makes objects self-verifying (threat model §4) and what bounds collision resistance (TM-R07).

**Inputs & Assumptions:**
- `ciphertext` (bytes): Trust: any; hashing is safe on untrusted input.
- `hex_len` (int): 12 or 32, else `ValueError` (L187-L188). Callers pass `int(self.id_hex_len or 12)` (`Vault__Object_Store.py:L143`) or the width read off an existing id (`object_id_matches` L203, `Vault__Inspector.py:L58`).

**Outputs & Effects:** deterministic string; pure (`test_Vault__Crypto.py::test_compute_object_id__*`, `test_Interop__Vectors.py::test_object_id_formats`).

**Cross-Function Dependencies:**
- Callers: `object_id_matches` L203, `Vault__Object_Store.py:L143`, `Vault__Inspector.py:L58`, `Step__Move__Build_Temp_Vault.py:L162` (default width 12 on move).
- Invariant coupling: the vault's `format` decides the width for NEW objects; readers verify "at the id's own width" (L186), so a format-2 vault still accepts 48-bit ids (`Known_Gaps::test_TM_R07__format_1_object_ids_are_48_bits`).

**Open Questions:** none.
