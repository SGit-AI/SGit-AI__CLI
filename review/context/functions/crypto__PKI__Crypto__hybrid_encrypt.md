## `hybrid_encrypt` in sgit_ai/crypto/PKI__Crypto.py (L80-L106)

```python
# L82-L87
data    = plaintext.encode() if isinstance(plaintext, str) else plaintext
aes_key = os.urandom(AES_KEY_BYTES)
iv      = os.urandom(GCM_IV_BYTES)
aesgcm     = AESGCM(aes_key)
ciphertext = aesgcm.encrypt(iv, data, None)
# L89-L94  wrapped_key = recipient_public_key.encrypt(aes_key, OAEP(MGF1(SHA256), SHA256, label=None))
# L96-L99  payload = dict(v=2, w=b64(wrapped_key), i=b64(iv), c=b64(ciphertext))
# L101-L104
if signing_private_key and signing_fingerprint:
    sig_raw      = self.sign(signing_private_key, ciphertext)
    payload['s'] = base64.b64encode(sig_raw).decode()
    payload['f'] = signing_fingerprint
# L106 return base64(json.dumps(payload))
```

**Purpose:** `sgit pki encrypt`: a fresh AES-256-GCM key per message, wrapped with the recipient's RSA-4096-OAEP key, optionally signed (ECDSA over the ciphertext) so the recipient can attribute it.

**Inputs & Assumptions:**
- `recipient_public_key`: resolved by `CLI__PKI.cmd_encrypt` L163-L169 from a keyring contact or own key by the fingerprint the user typed. Trust: the contact file in `~/.sg-send/keyring/` (written by `PKI__Keyring.add_contact` from a bundle the user imported).
- `plaintext` (str or bytes): user file content.
- `signing_private_key`, `signing_fingerprint`: both required for signing (L101, truthiness). The fingerprint is the SENDER's claim, copied verbatim into `f` (L104); it is `loaded['metadata']['signing_fingerprint']` on the CLI path (`CLI__PKI.py:L174-L180`).
- Implicit: `os.urandom`.

**Outputs & Effects:** base64 of JSON. Pure apart from randomness.
- What the signature covers: the GCM ciphertext bytes only (L102) — not `w`, not `i`, not `v`, not `f`. The recipient checks it over the same bytes (`hybrid_decrypt` L149). Because GCM authenticates `c` under the per-message key, and the signature binds `c` to the signer, a swap of `w` or `i` would make GCM decryption fail before the signature is consulted (L127 runs before L141).

**Block-by-Block:** L82 normalise; L83-L87 random key/IV, encrypt without AAD; L89-L94 wrap; L96-L99 assemble v2; L101-L104 optional signature; L106 encode.

**Cross-Function Dependencies:**
- Callees: `AESGCM.encrypt`, RSA `encrypt` (external-black-box), `sign` (internal L66-L69).
- Callers: `CLI__PKI.cmd_encrypt` L178.
- Tests: `test_PKI__Crypto.py::Test_PKI__Crypto__Hybrid_Encryption`, `test_PKI__Crypto__Hardening.py::test_hybrid_encrypt__*`.

**Open Questions:** none.
