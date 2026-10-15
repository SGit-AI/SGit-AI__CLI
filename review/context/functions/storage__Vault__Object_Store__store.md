## `store` in sgit_ai/storage/Vault__Object_Store.py (L46-L58)

```python
# L47-L58
object_id = self._compute_id(ciphertext)
path      = self.object_path(object_id)
if os.path.isfile(path):
    with open(path, 'rb') as f:
        existing = f.read()
    if existing != ciphertext:
        raise Vault__Object_Collision_Error(object_id)
    return object_id
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f:
    f.write(ciphertext)
return object_id
```

**Purpose:** Content-addressed insert of a locally produced ciphertext (blob, tree, commit, tag). Idempotent on identical bytes; refuses to overwrite different bytes at the same (truncated) id (`Vault__Object_Collision_Error`, L11-L23; TM-R07).

**Inputs & Assumptions:**
- `ciphertext` (bytes): produced by `Vault__Crypto.encrypt` under the read key by the caller. Trust: trusted (local).
- Implicit: `self.id_hex_len` (12 default, L44; set to 32 on format-2 vaults by `Vault__Sync__Base._apply_vault_format` L362 and `Step__Clone__Download_Index` L108); `self.vault_path` (see `object_path`).
- Precondition: `self.crypto` set — the field has no default (L43), so Type_Safe auto-constructs one; callers pass `crypto=` anyway (`Vault__Sync__Base.py:L376`).

**Outputs & Effects:**
- Writes `bare/data/<id>` once; returns the id.
- Raises `Vault__Object_Collision_Error` when an existing file at the id differs (L52-L53).
- Reads the whole existing file into memory for the compare (L50-L51).

**Block-by-Block:**
- L47: `_compute_id` → `crypto.compute_object_id(ciphertext, int(self.id_hex_len or 12))` (L142-L143) → `'obj-cas-imm-' + sha256[:n]`.
- L49-L54: existence + byte-compare. `isfile` follows links; a planted symlink at the id (A6) is read through and compared; if equal, nothing written; if different → collision error, not an overwrite.
- L55-L57: `makedirs` + plain `open('wb')` — overwrite semantics never reached for an existing regular file (L49 branch), so only a non-existent path is written.

**Cross-Function Dependencies:**
- Callees: `_compute_id` L142, `object_path` L96, `Vault__Crypto.compute_object_id` L183-L190.
- Callers: `Vault__Sub_Tree` L227 (blobs), L326 (trees); `Vault__Commit` L76 (commits); `Vault__Sync__Tag` L129 (tags); `Migration__Tree_IV_Determinism` L288.
- Tests: `tests/unit/storage/test_Vault__Object_Store__Collision.py` (`test_store_is_idempotent_for_identical_content`, `test_store_raises_on_genuine_collision`), `tests/unit/objects/test_Vault__Object_Store.py`.

**Open Questions:** none specific; see `object_path` for the `vault_path` sanitisation question.
