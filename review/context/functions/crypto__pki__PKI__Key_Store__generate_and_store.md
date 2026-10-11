## `generate_and_store` in sgit_ai/crypto/pki/PKI__Key_Store.py (L13-L40)

```python
# L14-L29
enc_priv, enc_pub  = self.crypto.generate_encryption_key_pair()
sig_priv, sig_pub  = self.crypto.generate_signing_key_pair()
enc_fingerprint = self.crypto.compute_fingerprint(enc_pub)
sig_fingerprint = self.crypto.compute_fingerprint(sig_pub)
key_dir = self._key_dir(enc_fingerprint)
os.makedirs(key_dir, exist_ok=True)
Vault__Secret_File().write(os.path.join(key_dir, 'private_key.pem'),    self.crypto.export_private_key_pem(enc_priv, passphrase))
with open(os.path.join(key_dir, 'public_key.pem'), 'w') as f:    f.write(self.crypto.export_public_key_pem(enc_pub))
Vault__Secret_File().write(os.path.join(key_dir, 'signing_private.pem'), self.crypto.export_private_key_pem(sig_priv, passphrase))
with open(os.path.join(key_dir, 'signing_public.pem'), 'w') as f: f.write(self.crypto.export_public_key_pem(sig_pub))
# L31-L40 metadata.json (label, algorithm, key_size, both fingerprints, created) via plain open
```

**Purpose:** `sgit pki keygen`: creates the user's RSA-4096 encryption pair and P-256 signing pair under `~/.sg-send/keys/sha256_<16hex>/`, private halves passphrase-encrypted.

**Inputs & Assumptions:**
- `label` (str): user text; stored in metadata, printed later. Trust: untrusted content, no path use.
- `passphrase` (str): Trust: untrusted strength. `CLI__PKI.cmd_keygen` L30-L33 refuses an empty one, so here it is non-empty and `export_private_key_pem` encrypts (`PKI__Crypto.py:L37-L39`). The same passphrase protects both private keys.
- Implicit: `self.keys_dir : Safe_Str__Vault_Path` (L10) — sanitised path (see Key_Manager accessors record); set by `CLI__PKI.setup` L24 from `os.path.expanduser(sg_send_dir or '~/.sg-send')`.
- Precondition: `key_dir` does not already hold another key with the same fingerprint. `makedirs(exist_ok=True)` and the two `Secret_File` writes replace silently. 64-bit fingerprint collision is the only way to hit this with distinct keys; **nothing found** that checks.

**Outputs & Effects:**
- Directory created with umask mode; `private_key.pem` and `signing_private.pem` 0600 via `Vault__Secret_File` (L24, L27); `public_key.pem`, `signing_public.pem`, `metadata.json` written with plain `open('w')` (umask mode; public data).
- Returns the metadata dict (printed by the CLI, L36-L45 of CLI__PKI).
- Not transactional across the five files: an exception midway leaves a partial key directory that `list_keys` (needs `metadata.json`) would skip but `_key_dir` would treat as existing.

**Block-by-Block:** L14-L18 generate and fingerprint; L20-L21 directory; L23-L29 four PEMs; L31-L38 metadata; L40 return.

**Cross-Function Dependencies:**
- Callees: `PKI__Crypto.generate_*`, `compute_fingerprint`, `export_*_pem` (internal, source available), `Vault__Secret_File.write` (L14-L35 there), `_key_dir` (L103-L105).
- Callers: `CLI__PKI.cmd_keygen` L36.
- Tests: `tests/unit/pki/test_PKI__Key_Store.py::test_generate_and_store_creates_files`, `tests/qa/crypto/test_CLI__PKI.py::Test_CLI__PKI_Keygen`.

**Open Questions:** none.
