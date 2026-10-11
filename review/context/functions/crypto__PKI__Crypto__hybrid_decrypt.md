## `hybrid_decrypt` in sgit_ai/crypto/PKI__Crypto.py (L108-L155)

```python
# L110-L113
payload = json.loads(base64.b64decode(encoded_payload))
if payload.get('v') not in (1, 2): raise ValueError(...)
# L115-L127  unwrap with RSA-OAEP, AESGCM(aes_key).decrypt(iv, ciphertext, None)
# L129-L132  utf-8 decode, falling back to latin-1
# L134-L139  result = dict(plaintext, plaintext_bytes, signed=False, verified=False, signer=None, signing_fingerprint=payload.get('f') or None)
# L141-L153
if payload.get('s') and payload.get('f'):
    result['signed'] = True
    if contacts_keyring:
        sig_raw = base64.b64decode(payload['s'])
        contact = contacts_keyring.lookup_by_signing_fingerprint(payload['f'])
        if contact:
            try:
                signing_pub = self.import_public_key_pem(contact['signing_key_pem'])
                self.verify(signing_pub, sig_raw, ciphertext)
                result['verified'] = True
                result['signer']   = contact.get('label', '')
            except Exception:
                result['verified'] = False
```

**Purpose:** `sgit pki decrypt`: unwrap, decrypt, and report whether and by whom the message was signed. The three-state outcome (`signed`, `verified`, `signer`) is what the CLI prints (`CLI__PKI.py:L206-L210`).

**Inputs & Assumptions:**
- `recipient_private_key`: our RSA key, loaded with the user's passphrase (`CLI__PKI._load_key_pair_or_exit`).
- `encoded_payload` (str): Trust: **untrusted** (a file someone sent us). Parsing: `base64.b64decode` (lenient) then `json.loads`; `payload['w']`/`['i']`/`['c']` are indexed directly (L115-L117) so a missing field is a `KeyError`, not a `ValueError`. `v=1` is accepted and handled identically to `v=2` (L112).
- `contacts_keyring`: anything with `lookup_by_signing_fingerprint`; the CLI passes `PKI__Known_Keys` (`CLI__PKI.py:L194-L195`), so OWN keys are candidates too (a self-signed message verifies as "signer = own label").
- Implicit: the keyring files on disk.

**Outputs & Effects:**
- Returns the result dict. `plaintext` is a lossy text rendering (latin-1 fallback, L132) and `plaintext_bytes` the exact bytes (L135); the CLI writes `plaintext_bytes` via `Vault__Secret_File` (0600) at `CLI__PKI.py:L204`.
- Raises on bad base64/JSON, unsupported version, RSA padding failure (`ValueError`), GCM failure (`InvalidTag`).
- `signing_fingerprint` in the result is the payload's own claim (L139), returned whether or not it verified.

**Block-by-Block:**

```python
# L119-L127 unwrap and decrypt
```
- **Establishes:** `ciphertext` is authentic under `aes_key`, and `aes_key` was wrapped to our RSA key. Says nothing about who wrapped it.
- **Depended on by:** the signature step, which runs only after this succeeds.

```python
# L141-L153 signature
```
- **What:** `signed` means the fields are present; `verified` means a known key with the CLAIMED fingerprint validated the signature over `ciphertext`.
- **Assumes:** the contact's `signing_fingerprint` really is the fingerprint of `signing_key_pem`. Established at import time by `CLI__PKI.cmd_import` (L86-L87 recompute from the PEM) — not re-checked here. A keyring file edited by hand is trusted as written (A6 scope).
- **Assumes:** `lookup_by_signing_fingerprint` returns the right contact when several share a signing fingerprint. `PKI__Keyring.lookup_by_signing_fingerprint` returns the first in sorted file order (L50-L53); `PKI__Known_Keys` prefers contacts over own keys (L28-L34).
- **Establishes:** `verified=False` on ANY exception (L152-L153), including a `KeyError` for a contact without `signing_key_pem` (contacts imported from a bundle with no `sign` field get `''`, `CLI__PKI.py:L84-L92`, which then fails at `import_public_key_pem`). The reason is not surfaced.

**Cross-Function Dependencies:**
- Callees: RSA `decrypt`, `AESGCM.decrypt` (external-black-box); `import_public_key_pem`, `verify` (internal); `contacts_keyring.lookup_by_signing_fingerprint` (internal: `PKI__Keyring.py:L50-L53` / `PKI__Known_Keys.py:L28-L34`).
- Callers: `CLI__PKI.cmd_decrypt` L194.
- Tests: `test_PKI__Crypto__Hardening.py::test_hybrid_encrypt_decrypt__with_signature_and_keyring`, `::test_hybrid_decrypt__bad_signature_sets_verified_false_lines_150_151`, `test_PKI__Crypto.py::test_unsupported_version_fails`, `::test_wrong_key_decrypt_fails`.

**Open Questions:** none.
