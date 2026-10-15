## `decrypt` in sgit_ai/crypto/Vault__Crypto.py (L301-L305)

```python
# L301-L305
def decrypt(self, key: bytes, data: bytes) -> bytes:
    iv         = data[:GCM_IV_BYTES]
    ciphertext = data[GCM_IV_BYTES:]
    aesgcm     = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, None)
```

**Purpose:** The one AES-256-GCM decryption. Everything read from the host or from `bare/` is decrypted here, so this is where integrity against a non-key-holder is established (threat model §5 row 1).

**Inputs & Assumptions:**
- `key` (bytes): trusted (derived/imported); same length note as `encrypt`.
- `data` (bytes): Trust: **untrusted** — bytes served by the host or read from disk. Nothing here checks length; `data[:12]` on shorter input yields a short nonce and `AESGCM.decrypt` raises (`test_Vault__Crypto__Hardening.py::test_decrypt__empty_data_fails`, `::test_decrypt__iv_only_no_ciphertext_fails`).

**Outputs & Effects:**
- Returns plaintext bytes, or raises `cryptography.exceptions.InvalidTag` (wrong key, modified tag/body/iv, truncation: `test_Vault__Crypto__Hardening.py::Test_Vault__Crypto__Tampering`, `test_Vault__Crypto.py::test_decrypt__wrong_key_fails`).
- Pure.
- Postcondition on success: the plaintext was produced by someone holding `key`. It says nothing about WHICH file id or vault the ciphertext belongs to (no AAD, L305; TM-R03) nor about freshness.

**Block-by-Block:** split (L302-L303), decrypt (L304-L305). No AAD.

**Cross-Function Dependencies:**
- Callee `AESGCM.decrypt` (external-black-box).
- Callers: ~45 sites. Several wrap the call in `try/except Exception` and treat failure as "not present / not a key" (`Vault__Key_Fetch._is_public_key` L54-L58, `Vault__Diff` etc.); others let `InvalidTag` propagate (`Secrets__Store._load_all` L56 → `test_Secrets__Store.py::test_wrong_passphrase_fails`; `Vault__Key_Manager.load_public_key` L37).
- Invariant coupling: callers who `json.loads` the result (e.g. `Vault__Key_Manager.load_public_key` L37) treat the decrypted JSON as trusted structure; that trust is valid only against actors without the read key.

**Open Questions:** none.
