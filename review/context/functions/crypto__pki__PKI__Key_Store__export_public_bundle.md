## `export_public_bundle` in sgit_ai/crypto/pki/PKI__Key_Store.py (L76-L93)

```python
# L77-L93
key_dir = self._key_dir(fingerprint)
if not os.path.isdir(key_dir): return None
... read public_key.pem, signing_public.pem, metadata.json ...
return dict(v=1, encrypt=enc_pem, sign=sig_pem, label=metadata.get('label', ''),
            fingerprint=metadata['encryption_fingerprint'], signing_fingerprint=metadata['signing_fingerprint'])
```

**Purpose:** The shareable public bundle (`sgit pki export`) and the source `PKI__Known_Keys._own_key` uses to treat our own keys like contacts.

**Inputs & Assumptions:** `fingerprint` — same unvalidated path rule as `load_key_pair`; here only public files and metadata are READ. `metadata['encryption_fingerprint']` / `['signing_fingerprint']` are indexed directly (L92-L93): a hand-edited metadata without them → `KeyError`.

**Outputs & Effects:** dict or `None`. The fingerprints in the bundle are the STORED claims from metadata, not recomputed from the PEMs; `CLI__PKI.cmd_import` on the receiving side recomputes them (L80-L87), so a tampered bundle cannot plant a wrong fingerprint in a keyring.

**Cross-Function Dependencies:** `_key_dir`. Callers: `CLI__PKI.cmd_export` L56, `PKI__Known_Keys._own_key` L37. Tests: `test_PKI__Key_Store.py::test_export_public_bundle*`.

**Open Questions:** none.
