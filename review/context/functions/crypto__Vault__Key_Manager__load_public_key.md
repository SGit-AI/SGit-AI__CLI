## `load_public_key` in sgit_ai/crypto/Vault__Key_Manager.py (L33-L38)

```python
# L34-L38
path       = self._key_path(key_id)
with open(path, 'rb') as f:
    ciphertext = f.read()
data = json.loads(self.crypto.decrypt(read_key, ciphertext))
return self.pki.import_public_key_pem(data['pem'])
```

**Purpose:** Reads and decrypts a branch public key from `bare/keys/<key_id>`. It is the verification path's source of truth for "which key signed this commit" (`Vault__Signatures.py:L35-L38`, `Vault__Sync__Tag.py:L207`).

**Inputs & Assumptions:**
- `key_id` (str): from a commit's `author_key_id` / a branch's `public_key_id` (host-served, read-key-encrypted index). Callers check `key_exists` first (`Vault__Signatures.py:L35`, `Vault__Sync__Tag.py:L202-L204`). Shape: `Safe_Str__Key_Id` on the schema; nothing here.
- `read_key` (bytes).
- The file: written by `store_public_key`, by `Vault__Key_Fetch` (host blob), or by clone/pull download. Trust: authentic under the read key — i.e. anyone with the read key could have produced it (TM-R01, `Known_Gaps::test_TM_R01__forged_commit_is_pulled_and_verifies`).

**Outputs & Effects:**
- Returns a public key object, or raises: `FileNotFoundError`, `InvalidTag` (wrong key / tampered), `json` errors, `KeyError('pem')`, or `ValueError` from `load_pem_public_key` (a legacy PRIVATE file at this id holds a private PEM and fails here). `type` is NOT checked (contrast `Vault__Key_Fetch._is_public_key` L57).
- Pure read.

**Cross-Function Dependencies:**
- Callees: `decrypt` (`Vault__Crypto.py:L301-L305`), `import_public_key_pem` (`PKI__Crypto.py:L48-L49`), `_key_path`.
- Callers: `Vault__Signatures.py:L38`, `Vault__Sync__Tag.py:L207`. Both are "verify" paths; how each handles exceptions is outside this slice.
- Tests: `test_Vault__Key_Manager.py::test_store_and_load_public_key`.

**Open Questions:**
- unclear; need to inspect `Vault__Signatures.status_of` (L30-L45) for how an exception here is classified (`no-key` vs `bad`).
