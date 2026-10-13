## `encrypt_deterministic` in sgit_ai/crypto/Vault__Crypto.py (L257-L265)

```python
# L264-L265
iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]
return self.encrypt(key, plaintext, iv=iv)
```

**Purpose:** Synthetic-IV encryption so that an unchanged subtree encrypts to identical bytes and therefore the same content address across commits (docstring L258-L262). Used for tree objects (`Vault__Sub_Tree.py:L325`) and, via `encrypt_metadata_deterministic`, for tree entry names/sizes/hashes/types (`Vault__Sub_Tree.py:L60-L76, L99-L102, L299`) and in the tree-IV migration (`Migration__Tree_IV_Determinism.py:L43,L284`) and `vault move` re-encryption (`Step__Move__Build_Temp_Vault.py:L201,L325`).

**Inputs & Assumptions:**
- `key` (bytes): the read key. Trust: trusted. It is used both as the HMAC key (L264) and the AES key (L265): one key, two algorithms.
- `plaintext` (bytes): tree JSON or an entry field. Trust: semi-trusted (built by the code from user file names).
- Precondition: for GCM, no two DIFFERENT plaintexts may share an IV under one key. Here the IV is the first 96 bits of `HMAC-SHA256(key, plaintext)`, so two distinct plaintexts collide only on a 96-bit HMAC-prefix collision. Nothing checks this; it is a property of the construction. **nothing found** beyond the construction itself.

**Outputs & Effects:**
- Returns `iv || ct || tag` deterministic in (key, plaintext) (`test_Vault__Crypto__Deterministic.py::test_determinism__same_key_same_plaintext_same_ciphertext`, `::test_iv_derivation__equals_hmac_sha256_prefix`, browser vector `::test_browser_interop_vector__exact_hex_output`).
- Postcondition: equal ciphertext ⇔ equal plaintext under the same key. A host or read-key holder therefore learns when a tree or an entry field is unchanged between commits (the dedup the docstring wants; threat model §5 row 1 "does not guarantee ... which objects change").
- Pure.

**Block-by-Block:** L264 derive IV, L265 delegate to `encrypt` with that IV.

**Cross-Function Dependencies:**
- Callee `encrypt` (internal, L294-L299): honours the supplied IV without checks.
- Callers: `encrypt_metadata_deterministic` (L270), `Vault__Sub_Tree.build_from_flat`-family (L325), migration and move steps.
- Invariant coupling: blobs MUST keep random IVs (L262) — `Vault__Sub_Tree.py:L226` calls `encrypt` (random) for blob content; `test_Vault__Crypto.py::test_compute_object_id__same_plaintext_different_ciphertext` records that two blobs with equal content get different ids.
- `decrypt` needs no change: the IV is carried in the output.

**Open Questions:** none.
