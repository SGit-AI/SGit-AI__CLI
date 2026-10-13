## `encrypt_metadata_deterministic` in sgit_ai/crypto/Vault__Crypto.py (L267-L271)

```python
# L269-L271
data       = plaintext.encode('utf-8')
ciphertext = self.encrypt_deterministic(key, data)
return base64.b64encode(ciphertext).decode('ascii')
```

**Purpose:** Deterministic encryption of tree-entry fields (`name_enc`, `size_enc`, `content_hash_enc`, `content_type_enc`: `Vault__Sub_Tree.py:L60-L76, L99-L102, L299`) so unchanged entries serialise identically and tree objects deduplicate.

**Inputs & Assumptions:** `key` (read key), `plaintext` (str; a file NAME, a size, a hash or a content type — user-controlled content).

**Outputs & Effects:** base64; equal (key, plaintext) ⇒ equal output. So within one vault, two entries with the same file name, or the same size, encrypt identically: a read-key-less observer can tell "these two entries have equal names/sizes" (consequence of the dedup design; see `encrypt_deterministic`). Tests: `test_Vault__Crypto__Deterministic.py::test_metadata_determinism__*`, `::test_metadata_browser_interop_vector__exact_b64_output`.

**Cross-Function Dependencies:** Callee `encrypt_deterministic` (internal). Decrypted by `decrypt_metadata`. Callers: `Vault__Sub_Tree`, `Step__Move__Build_Temp_Vault.py:L201,L325`.

**Open Questions:** none.
