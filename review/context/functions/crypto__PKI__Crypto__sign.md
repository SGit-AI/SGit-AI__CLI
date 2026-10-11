## `sign` in sgit_ai/crypto/PKI__Crypto.py (L66-L69)

```python
# L67-L69
der_sig = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
r, s    = asym_utils.decode_dss_signature(der_sig)
return r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
```

**Purpose:** ECDSA P-256/SHA-256 signature in the raw 64-byte `r||s` form Web Crypto uses (comment L64). Signs commits (`Vault__Commit.py:L71`), tags (`Vault__Sync__Tag.py:L127`), change packs (`Vault__Change_Pack.py:L60`), PKI files (`CLI__PKI.py:L111`) and hybrid payloads (`hybrid_encrypt` L102).

**Inputs & Assumptions:** `private_key` (EC P-256 object; an RSA key would raise at L67 since `ec.ECDSA` is passed), `data` (bytes). The caller is responsible for what `data` is: canonical signing bytes for commits (`Vault__Commit.signing_bytes`), the ciphertext for hybrid payloads.

**Outputs & Effects:** 64 bytes (`test_PKI__Crypto.py::test_sign_returns_64_bytes`). ECDSA uses a per-signature random nonce inside `cryptography`; not controlled here.

**Cross-Function Dependencies:** Callee `private_key.sign` / `decode_dss_signature` (external-black-box). `verify` (L71-L76) is the inverse. Interop: `test_Interop__Vectors.py::test_commit_signing_bytes_and_signature`.

**Open Questions:** none.
