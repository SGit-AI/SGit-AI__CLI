## `export_private_key_pem` in sgit_ai/crypto/PKI__Crypto.py (L36-L44)

```python
# L37-L44
encryption = (serialization.BestAvailableEncryption(passphrase.encode())
              if passphrase
              else serialization.NoEncryption())
return private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption).decode()
```

**Purpose:** Serialises a private key to PKCS#8 PEM, encrypted under `passphrase` when one is given and in the clear otherwise. It is the only place private key material becomes bytes that reach disk.

**Inputs & Assumptions:**
- `private_key`: RSA or EC key object. Trusted (just generated or just loaded).
- `passphrase` (str or None): Trust: **untrusted** strength. The test at L38 is truthiness: `''` and `None` both give `NoEncryption()`. Who decides:
  - `PKI__Key_Store.generate_and_store` L24, L27 passes the user's passphrase; `CLI__PKI.cmd_keygen` L30-L33 exits on an empty one, so on that path the PEM is always encrypted.
  - `Vault__Key_Manager.store_private_key` L41 and `store_private_key_locally` L58 pass NO passphrase: clone signing keys are written as unencrypted PKCS#8, protected only by file mode (0600 via `Vault__Secret_File`) and, for the legacy `bare/keys` form, by the read key.

**Outputs & Effects:** PEM text. `BestAvailableEncryption` picks the library's current PKCS#8 PBES scheme and iteration count; nothing in this repo pins them (interop with a browser is not claimed for private PEMs).

**Block-by-Block:** L37-L39 choose encryption; L40-L44 serialise.

**Cross-Function Dependencies:**
- Callee `private_bytes` (external-black-box).
- Callers listed above. Tests: `test_PKI__Crypto__Hardening.py::test_export_private_key__no_passphrase`, `::test_export_private_key__with_passphrase`, `test_PKI__Crypto.py::test_export_import_private_key_with_passphrase`.

**Open Questions:** none.
