## `add_contact` in sgit_ai/crypto/pki/PKI__Keyring.py (L10-L21)

```python
# L13-L21
contact = dict(label=label, fingerprint=fingerprint, signing_fingerprint=signing_fingerprint,
               public_key_pem=public_key_pem, signing_key_pem=signing_key_pem)
path = self._contact_path(fingerprint)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump(contact, f, indent=2)
```

**Purpose:** Persists an imported contact (someone else's public bundle) to `~/.sg-send/keyring/sha256_<16hex>.json`. These files are what `hybrid_decrypt` and `sgit pki verify` consult to turn a signature into a name.

**Inputs & Assumptions:**
- `fingerprint`, `signing_fingerprint`: on the only production path (`CLI__PKI.cmd_import` L80-L92) both are RECOMPUTED from the PEMs (`compute_fingerprint`), not taken from the bundle — so the file name and the stored fingerprints are bound to the PEM content at import time. Nothing in `add_contact` itself re-checks that binding; a later hand edit of the JSON is trusted by every reader (A6 scope).
- `label`: whatever the importer typed (`CLI__PKI.py:L126-L128` docstring says scripts pin the fingerprint for that reason).
- `signing_key_pem` defaults to `''` when the bundle has no `sign` field; `hybrid_decrypt` then fails verification for that contact (its L148 raises on an empty PEM → `verified=False`).

**Outputs & Effects:** umask-mode JSON file (public data); overwrites an existing contact with the same encryption fingerprint silently.

**Cross-Function Dependencies:** `_contact_path` (L56-L58). Caller: `CLI__PKI.cmd_import` L90. Tests: `tests/unit/pki/test_PKI__Keyring.py::test_add_and_get_contact`.

**Open Questions:** none.
