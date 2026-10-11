## `_own_key` in sgit_ai/crypto/pki/PKI__Known_Keys.py (L36-L45)

```python
# L37-L45
bundle = self.key_store.export_public_bundle(metadata['encryption_fingerprint'])
if not bundle: return None
return dict(label=bundle.get('label', ''), fingerprint=bundle['fingerprint'], public_key_pem=bundle['encrypt'],
            signing_key_pem=bundle['sign'], signing_fingerprint=bundle['signing_fingerprint'], source=SOURCE__OWN_KEY)
```

**Purpose:** Shapes one of our own key pairs like a keyring contact so callers need one code path.

**Inputs & Assumptions:** `metadata` (dict) from `PKI__Key_Store.list_keys` — our own `metadata.json`; `metadata['encryption_fingerprint']` indexed directly (KeyError on a damaged file). The fingerprint is then used by `export_public_bundle` → `_key_dir` to build a path: it came from OUR metadata, so shape is as keygen wrote it.

**Outputs & Effects:** dict or `None` (when the directory vanished between `list_keys` and here). Pure read.

**Cross-Function Dependencies:** `PKI__Key_Store.export_public_bundle` (L76-L93). Callers: L24, L33.

**Open Questions:** none.
