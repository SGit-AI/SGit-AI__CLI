## `load_key_pair` in sgit_ai/crypto/pki/PKI__Key_Store.py (L54-L74)

```python
# L55-L68
key_dir = self._key_dir(fingerprint)
if not os.path.isdir(key_dir):
    return None
with open(os.path.join(key_dir, 'private_key.pem'), 'r') as f:    enc_priv = self.crypto.import_private_key_pem(f.read(), passphrase)
with open(os.path.join(key_dir, 'public_key.pem'), 'r') as f:     enc_pub  = self.crypto.import_public_key_pem(f.read())
with open(os.path.join(key_dir, 'signing_private.pem'), 'r') as f: sig_priv = self.crypto.import_private_key_pem(f.read(), passphrase)
with open(os.path.join(key_dir, 'signing_public.pem'), 'r') as f:  sig_pub  = self.crypto.import_public_key_pem(f.read())
with open(os.path.join(key_dir, 'metadata.json'), 'r') as f:       metadata = json.load(f)
```

**Purpose:** Loads both key pairs for `sgit pki sign|encrypt --sign|decrypt`, decrypting the private PEMs with the user's passphrase.

**Inputs & Assumptions:**
- `fingerprint` (str): `args.fingerprint` from the CLI (`CLI__PKI.py:L106,L174,L190` via `_load_key_pair_or_exit` L212-L215). Trust: **untrusted** (user argv). `_key_dir` only replaces `:` with `_` and joins (L104-L105); a value with `/`, `..` or an absolute path makes `key_dir` point outside `keys_dir` (`os.path.join` drops the prefix on an absolute second argument). This function then reads five fixed file names under that directory and tries to decrypt them with the passphrase. **nothing found** validating the fingerprint's shape (`sha256:<16hex>`) on this path. A `Safe_Str__Key_Fingerprint` exists in `sgit_ai/safe_types/` but is not used here.
- `passphrase` (str): from `SG_SEND_PASSPHRASE` or `getpass` (`CLI__PKI.py:L213`).

**Outputs & Effects:**
- `None` when the directory is missing (L56-L57); the CLI reports "not found" (L219-L221).
- Wrong passphrase → `ValueError`/`TypeError` from `import_private_key_pem` (caught at `CLI__PKI.py:L216`). A missing individual file → `FileNotFoundError`, NOT caught by that `except (ValueError, TypeError)` — propagates as a traceback.
- Both private keys unlocked in memory for the rest of the command.
- Pure read.

**Cross-Function Dependencies:** `_key_dir`, `PKI__Crypto.import_*` (internal). Callers: `CLI__PKI._load_key_pair_or_exit` L215. Tests: `test_PKI__Key_Store.py::test_load_key_pair`, `::test_load_key_pair_wrong_passphrase`, `::test_load_key_pair_missing`.

**Open Questions:**
- unclear; need to inspect the argparse definition for `pki sign/encrypt/decrypt --fingerprint` in `CLI__Main` for any `type=` validation of the fingerprint argument.
