## `save_branch_index` in sgit_ai/storage/Vault__Branch_Manager.py (L76-L86)

```python
# L78-L86
if not index_file_id:
    index_file_id = 'idx-pid-muw-' + secrets.token_hex(6)
data       = Vault__Index_Reader().serialize(index)
ciphertext = self.crypto.encrypt(read_key, data)
path       = self.storage.index_path(directory, index_file_id)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f: f.write(ciphertext)
```

**Purpose:** Encrypt and write the local copy of the branch index (`bare/indexes/<id>`), with carried tag entries put back (L81 comment, B1).

**Inputs & Assumptions:**
- `index` (`Schema__Branch_Index`): built by the caller; `serialize` → `to_json` (carried → `tags`) → `json.dumps`.
- `index_file_id`: callers pass `c.branch_index_file_id` (HMAC-derived; `Vault__Sync__Format.py:L61,L66`, `Vault__Sync__Push.py:L851`, `Vault__Sync__Tag.py:L180`, `Vault__Index_Sync.py:L288`, `Vault__Branch_Switch.py:L111,L240,L288`, `Step__Clone__*`) or none (`tests/unit/sync/test_Vault__Branch_Manager.py::test_save_branch_index_without_index_file_id_line_79`). A random id would create an index file nothing reads (the id is derived, not discovered) — only reachable from tests as far as callers show.
- Precondition on path: `directory` raw user string; joined via `Vault__Storage.index_path` L125-L126 with `index_file_id` unvalidated (HMAC hex at every production caller).

**Outputs & Effects:** Overwrites the index file (plain `open('wb')`, follows a planted link — A6). No atomicity: an interrupted write leaves a truncated ciphertext that `load_branch_index` cannot decrypt (every command then fails at `_apply_vault_format` L357 → swallowed → format 1, and at the next explicit load → raises). `nothing found` that writes via temp+rename here (contrast `write_local_config`).

**Cross-Function Dependencies:** Callees `Vault__Index_Reader.serialize` L108, `Vault__Crypto.encrypt`, `Vault__Storage.index_path`. Callers above (~12). Shared file with `load_branch_index` and with `Vault__Verified_Write.save` (which writes `bare/indexes/<id>` from the host on clone/pull without parsing it).

**Open Questions:**
- Non-atomic index write (see above) — whether any caller guards against partial writes.
