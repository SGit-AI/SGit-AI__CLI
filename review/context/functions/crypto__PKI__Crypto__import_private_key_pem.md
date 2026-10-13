## `import_private_key_pem` in sgit_ai/crypto/PKI__Crypto.py (L51-L53)

```python
# L52-L53
pwd = passphrase.encode() if passphrase else None
return serialization.load_pem_private_key(pem_str.encode(), password=pwd)
```

**Purpose:** Inverse of `export_private_key_pem`.

**Inputs & Assumptions:**
- `pem_str` (str): from `.sg_vault/local/<key_id>.pem` (`Vault__Key_Manager.load_private_key_locally` L67), from a read-key-decrypted `bare/keys` file (`load_private_key` L54), or from `~/.sg-send/keys/<fp>/*.pem` (`PKI__Key_Store.load_key_pair` L60, L64). Trust: the first two are local files the same user wrote; the third too.
- `passphrase`: same truthiness rule as export. Wrong passphrase → `ValueError`; passphrase given for an unencrypted PEM → `TypeError` (both caught at `CLI__PKI.py:L216`).

**Outputs & Effects:** key object or exception. Pure.

**Cross-Function Dependencies:** Callee `load_pem_private_key` (external-black-box). Callers above. Tests: `test_PKI__Crypto.py::test_wrong_passphrase_fails`, `test_PKI__Key_Store.py::test_load_key_pair_wrong_passphrase`.

**Open Questions:** none.
