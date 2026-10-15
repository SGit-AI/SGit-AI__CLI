## `load_private_key` in sgit_ai/crypto/Vault__Key_Manager.py (L49-L54)

```python
# L50-L54
path       = self._key_path(key_id)
with open(path, 'rb') as f:
    ciphertext = f.read()
data = json.loads(self.crypto.decrypt(read_key, ciphertext))
return self.pki.import_private_key_pem(data['pem'])
```

**Purpose:** Reads a legacy private key from `bare/keys/` under the read key. **No production caller**: grep over `sgit_ai/` shows only the definition. The security test `Known_Gaps::test_TM_R27__a_legacy_named_private_key_stays_readable_until_the_vault_is_moved` (L91-L103) uses it to prove a read-key-only adversary can recover such a key from the host.

**Inputs & Assumptions:** as `load_public_key`; `import_private_key_pem` with no passphrase (L54 → `PKI__Crypto.py:L52` `None`), matching how `store_private_key` wrote it.

**Outputs & Effects:** private key object or exception. `type` not checked.

**Cross-Function Dependencies:** `decrypt`, `import_private_key_pem`, `_key_path`. Test: `test_Vault__Key_Manager.py::test_store_and_load_private_key`.

**Open Questions:** none.
