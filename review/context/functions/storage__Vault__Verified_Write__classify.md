## `classify` in sgit_ai/storage/Vault__Verified_Write.py (L43-L66)

```python
# L60-L66
if not self.is_content_addressed(file_id):
    return self.VERIFIED
if self.crypto is None:
    self.crypto = Vault__Crypto()
if self.crypto.object_id_matches(file_id, data or b''):
    return self.VERIFIED
return self.REFUSED
```

**Purpose:** The integrity verdict, without writing. Strictly content-address based; the docstring (L47-L58) records why the former "but it decrypts under my key" fallback was removed (two authentic objects swapped between ids both decrypt — review finding A1) and that pre-rewrite moved vaults are therefore REFUSED until `sgit vault move` normalises them.

**Inputs & Assumptions:** `file_id` untrusted; `data` untrusted bytes (or `None` → `b''`, L64); `read_key` ignored (kept in the signature for callers). Implicit: `self.crypto` may be `None` on a bare `Vault__Verified_Write()` (`Step__Move__Validate_Local.py:L177`, `Vault__Verified_Write()` in `is_store_path` is a different class) — defaulted at L62-L63.

**Outputs & Effects:** Pure; returns one of two string constants (L40-L41).

**Cross-Function Dependencies:**
- Callee `is_content_addressed` L25-L27: `rsplit('/',1)[-1].startswith('obj-cas-imm-')`.
- Callee `Vault__Crypto.object_id_matches` L200-L203 → `object_id_hex_len` L192-L198 (12 or 32 else 0) → `compute_object_id` L183-L190 (`sha256(ciphertext).hexdigest()[:n]`). A 13- or 31-hex id is a width of 0 → never matches → REFUSED. Non-`obj-cas-imm-` names in `bare/data/` (e.g. the `obj-<12hex>` names `Vault__Change_Pack` creates at L44-L48 and `Vault__GC` stores via `store_raw` L82) are **not** content-addressed by this test and would be VERIFIED unchecked if a host served them under `bare/data/obj-xxxx`.
- Callers: `verify` L70, `save` L78.

**Open Questions:**
- The `obj-<hex>` (non-`cas-imm`) naming used by change packs: whether such names can ever arrive from the host (nothing in the fetch paths read filters them; `Vault__Object_Store.all_object_ids` L125 only lists `obj-cas-imm-*`, so they would be invisible to fsck/gc listings).
