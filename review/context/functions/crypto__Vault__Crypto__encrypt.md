## `encrypt` in sgit_ai/crypto/Vault__Crypto.py (L294-L299)

```python
# L294-L299
def encrypt(self, key: bytes, plaintext: bytes, iv: bytes = None) -> bytes:
    if iv is None:
        iv = os.urandom(GCM_IV_BYTES)
    aesgcm     = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    return iv + ciphertext
```

**Purpose:** The one AES-256-GCM encryption primitive. Every object, ref, index, key file, cache entry, tag, branch index and the credential store go through it (callers in `sgit_ai/storage/*`, `core/actions/*`, `secrets/Secrets__Store.py:L62`, `crypto/Vault__Key_Manager.py:L27,L43`).

**Inputs & Assumptions:**
- `key` (bytes): Trust: trusted (derived or imported). Precondition: 16, 24 or 32 bytes — `AESGCM.__init__` raises for other lengths; nothing here requires 32. Callers obtain 32 bytes from PBKDF2/HKDF; `import_read_key` could supply 16 or 24 (see that record).
- `plaintext` (bytes): Trust: varies (file content, JSON the code built).
- `iv` (bytes or None): None → 12 random bytes (L296). Non-None only from `encrypt_deterministic` (L265). Precondition when supplied: unique per (key, plaintext) — `encrypt_deterministic` makes it a function of both.
- Implicit: `os.urandom`.

**Outputs & Effects:**
- Returns `iv || ciphertext || tag` (12 + len + 16; `test_Vault__Crypto__Hardening.py::test_ciphertext_length__includes_iv_and_tag`).
- No associated data (`None`, L298): the ciphertext is not bound to its file id or any context. This is the mechanism behind TM-R03 (host can serve one ref's ciphertext under another id).
- Ciphertext length reveals plaintext length exactly (TM-R08; `Known_Gaps::test_TM_R08__ciphertext_reveals_exact_plaintext_size`).
- Pure apart from randomness.

**Block-by-Block:**

```python
# L295-L296
if iv is None: iv = os.urandom(GCM_IV_BYTES)
```
- **What:** Fresh nonce per call for the random path.
- **Assumes:** `os.urandom` is a CSPRNG. Test `::test_encrypt__different_iv_per_call`.

```python
# L297-L299
aesgcm = AESGCM(key); ciphertext = aesgcm.encrypt(iv, plaintext, None); return iv + ciphertext
```
- **What:** Encrypt and prepend nonce.
- **Establishes:** the wire format `decrypt` (L302-L303) and the browser expect (`test_Vault__Crypto.py::test_encrypt__interop_vector`).

**Cross-Function Dependencies:**
- Callee `AESGCM.encrypt` (external-black-box).
- Callers (direct): `encrypt_metadata` L254, `encrypt_deterministic` L265, plus ~15 storage/action sites. The key passed is the READ key in every production call (`c.read_key`, `read_key`, `new_key`) or the credential-store master key.
- Shared state: none.
- Invariant coupling: the symmetric fact of threat model §1 ("whoever can decrypt can also encrypt") is this function: it has no notion of a writer identity.

**Open Questions:** none.
