## `lookup_by_signing_fingerprint` in sgit_ai/crypto/pki/PKI__Known_Keys.py (L27-L34)

```python
# L28-L34
contact = self.keyring.lookup_by_signing_fingerprint(signing_fingerprint)
if contact: return dict(contact, source=SOURCE__CONTACT)
for metadata in self.key_store.list_keys():
    if metadata.get('signing_fingerprint') == signing_fingerprint:
        return self._own_key(metadata)
return None
```

**Purpose:** Resolve a SIGNING fingerprint (the `f` field of a hybrid payload, or the `fingerprint` in a `.sig` file) to a record, contacts first then own keys. It is the `contacts_keyring` object `hybrid_decrypt` receives (`CLI__PKI.py:L194-L195`) and what `cmd_verify` uses (L136).

**Inputs & Assumptions:** `signing_fingerprint` (str): Trust: **untrusted** — it is the sender's claim inside the payload / sig file. Used only for dict-equality comparisons (`PKI__Keyring.lookup_by_signing_fingerprint` L50-L53 scans; no path built from it), so an arbitrary value only yields `None`.

**Outputs & Effects:** record or `None`. Pure. Precedence: contact over own key; among contacts, first in sorted filename order (see Keyring accessors).

**Cross-Function Dependencies:** `PKI__Keyring.lookup_by_signing_fingerprint`, `PKI__Key_Store.list_keys`, `_own_key`. Callers: `PKI__Crypto.hybrid_decrypt` L145 (duck-typed), `CLI__PKI.cmd_verify` L136. The `source` field is printed by `cmd_verify` (L150) so a self-signed file is labelled "own key".

**Open Questions:** none.
