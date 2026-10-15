## `derive_structure_key` in sgit_ai/crypto/Vault__Crypto.py (L236-L248)

```python
# L244-L248
hkdf = HKDF(algorithm=hashes.SHA256(), length=AES_KEY_BYTES, salt=None, info=STRUCTURE_KEY_INFO)
return hkdf.derive(read_key)
```

**Purpose:** Derives a one-way "structure key" from the read key (docstring L237-L242: meant to decrypt metadata but not blobs). **No production caller exists**: grep over `sgit_ai/` finds only the definition; callers are `tests/unit/crypto/test_Vault__Crypto__Structure_Key.py`.

**Inputs & Assumptions:**
- `read_key` (bytes): Trust: trusted (derived).
- Precondition: none enforced; HKDF accepts any length input.

**Outputs & Effects:** 32 bytes; pure. Fixed vector at `test_Vault__Crypto__Structure_Key.py::test_derive_structure_key_interop_vector`.

**Block-by-Block:** one HKDF call, `salt=None`, `info=b'sg-vault-v1:structure-key'` (L40).

**Cross-Function Dependencies:**
- Callee `HKDF.derive` (external-black-box).
- Callers: none in production. Metadata is encrypted under the READ key everywhere (`encrypt_metadata` L252-L255, `Vault__Sub_Tree.py:L60-L76`), and `test_Vault__Crypto__Structure_Key.py::test_metadata_encrypted_with_read_key_is_not_readable_via_structure_key` records that a structure key cannot read what the code actually writes.

**Open Questions:**
- unclear; whether the structure-key design is planned or abandoned. Its presence with no caller is a fact for the hunting phase to weigh, not a finding here.
