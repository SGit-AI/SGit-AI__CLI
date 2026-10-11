## `encrypt_metadata` in sgit_ai/crypto/Vault__Crypto.py (L252-L255)

```python
# L253-L255
data       = plaintext.encode('utf-8')
ciphertext = self.encrypt(read_key, data)
return base64.b64encode(ciphertext).decode('ascii')
```

**Purpose:** Random-IV encryption of a text field (commit messages: `Vault__Commit.py:L60`, `Step__Move__Build_Temp_Vault.py:L218,L333`) to a base64 string for embedding in JSON.

**Inputs & Assumptions:** `read_key` (bytes, trusted), `plaintext` (str: a commit message, untrusted content but the code's own choice to encrypt).

**Outputs & Effects:** base64 string; randomised per call (`encrypt` L296), so equal messages do not produce equal ciphertext — unlike `encrypt_metadata_deterministic`. Length leaks message length (TM-R08).

**Cross-Function Dependencies:** Callee `encrypt` (internal). Decrypted by `decrypt_metadata` (L273-L276). Test: `test_Vault__Crypto.py::test_encrypt_decrypt_metadata_round_trip`.

**Open Questions:** none.
