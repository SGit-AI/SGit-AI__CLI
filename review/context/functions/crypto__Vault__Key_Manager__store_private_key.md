## `store_private_key` in sgit_ai/crypto/Vault__Key_Manager.py (L40-L47)

```python
# L41-L47
pem  = self.pki.export_private_key_pem(private_key)
data = json.dumps({'type': 'private', 'pem': pem}).encode()
ciphertext = self.crypto.encrypt(read_key, data)
path = self._key_path(key_id)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f:
    f.write(ciphertext)
```

**Purpose:** Writes a PRIVATE signing key into `bare/keys/` encrypted under the READ key. This is the legacy mechanism behind TM-R02 (fixed) / TM-R27 (accepted): every read-key holder could decrypt and sign as the named branch. **No production caller remains**: grep over `sgit_ai/` finds only the definition; `Vault__Branch_Manager.create_named_branch` L36-L39 states the private half is deliberately not stored. Callers are tests that reproduce what older clients wrote (`tests/security/test_Security__Known_Gaps.py:L97`, `tests/security/test_Security__Fixed__Trust_And_Policy.py:L75`, `tests/unit/crypto/test_Vault__Key_Manager.py:L44`).

**Inputs & Assumptions:** `private_key` exported WITHOUT a passphrase (L41 → `PKI__Crypto.py:L38` falsy → `NoEncryption`), so the only protection is the read-key GCM layer. `key_id`, `read_key` as in `store_public_key`.

**Outputs & Effects:** umask-mode file write; not atomic. `type: 'private'` tag distinguishes it from public files; `_drop_shared_private_keys` (`Step__Move__Build_Temp_Vault.py:L427-L438`) nulls the index's `private_key_id` on move, and `test_vault_move_drops_a_legacy_named_private_key` checks the host then holds only `public` types.

**Cross-Function Dependencies:** as `store_public_key`. Kept so legacy vaults remain readable via `load_private_key`.

**Open Questions:** none.
