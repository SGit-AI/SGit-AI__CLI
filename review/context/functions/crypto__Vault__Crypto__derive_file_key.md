## `derive_file_key` in sgit_ai/crypto/Vault__Crypto.py (L287-L292)

```python
# L288-L292
hkdf = HKDF(algorithm=hashes.SHA256(), length=AES_KEY_BYTES, salt=None, info=HKDF_INFO_PREFIX + file_context)
return hkdf.derive(vault_key)
```

**Purpose:** Per-file subkey derivation (`info = b'sg-send-file-key' + file_context`, L17). **No production caller**: grep over `sgit_ai/` finds only the definition; callers are `tests/unit/crypto/test_Vault__Crypto.py::test_derive_file_key__*` and `test_Vault__Crypto__Hardening.py::Test_Vault__Crypto__HKDF_Edge_Cases`.

**Inputs & Assumptions:** `vault_key` (bytes), `file_context` (bytes); both trusted in the tests. No checks.

**Outputs & Effects:** 32 bytes; pure. Fixed vector at `test_Vault__Crypto.py::test_derive_file_key__interop_vector`.

**Cross-Function Dependencies:** Callee `HKDF.derive` (external-black-box). No callers in production: all objects are encrypted directly under the read key (`encrypt` callers across `sgit_ai/storage/`).

**Open Questions:**
- unclear; same as `derive_structure_key`: a documented interop primitive the code does not use.
