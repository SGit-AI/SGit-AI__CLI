## `lookup_by_fingerprint` in sgit_ai/crypto/pki/PKI__Known_Keys.py (L18-L25)

```python
# L19-L25
contact = self.keyring.get_contact(fingerprint)
if contact:
    return dict(contact, source=SOURCE__CONTACT)
for metadata in self.key_store.list_keys():
    if metadata.get('encryption_fingerprint') == fingerprint:
        return self._own_key(metadata)
return None
```

**Purpose:** Resolve an ENCRYPTION fingerprint to a public-key record, preferring imported contacts over own keys (docstring L10-L14: lets a machine encrypt to itself). Used by `sgit pki encrypt --recipient`.

**Inputs & Assumptions:** `fingerprint` (str): argv (`CLI__PKI.py:L163`). Passed to `PKI__Keyring.get_contact` unvalidated (see that record); compared by string equality against metadata on the own-key path.

**Outputs & Effects:** dict with `source` = `'contact'` or `'own key'`, or `None`. Pure read. Order rule: a contact with the same fingerprint as an own key shadows the own key.

**Cross-Function Dependencies:** `PKI__Keyring.get_contact` (L23-L28), `PKI__Key_Store.list_keys` (L42-L52), `_own_key` (L36-L45). Caller: `CLI__PKI.cmd_encrypt` L163. Tests: covered through `tests/qa/crypto/test_CLI__PKI.py::Test_CLI__PKI_Encrypt_Decrypt`.

**Open Questions:** none.
