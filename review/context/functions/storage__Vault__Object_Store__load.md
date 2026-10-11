## `load` in sgit_ai/storage/Vault__Object_Store.py (L84-L91)

```python
# L85-L91
path = self.object_path(object_id)
try:
    with open(path, 'rb') as f: return f.read()
except FileNotFoundError:
    raise Vault__Object_Missing_Error(f'object {object_id} is not in the local store') from None
```

**Purpose:** Read an object's ciphertext from `bare/data/<id>`; a missing object becomes `Vault__Object_Missing_Error` (a `FileNotFoundError` subclass, L26-L38) so every existing absent-object handler keeps working.

**Inputs & Assumptions:**
- `object_id` (str): joined unvalidated. Sources: decrypted tree entries (`Schema__Object_Tree_Entry.blob_id/tree_id : Safe_Str__Object_Id` — strict `^obj-cas-imm-(12|32 hex)$`), flat maps built from them (`Vault__Sub_Tree.flatten` L125 `str(entry.blob_id)`), commit ids from refs (`read_ref` → a JSON string with no schema validation — `Vault__Ref_Manager.py:L41-L42`), CLI-supplied ids via `resolve_id`. For the ref-derived path the id is whatever the (read-key-authentic) ref said; A3/A4 can make it any string, e.g. `../../local/vault_key` — `open` then reads that file and the caller tries to decrypt it, which fails under AES-GCM. The read itself is unguarded; `nothing found` that validates `commit_id` shape between `read_ref` and `load` in this slice (`Vault__Commit.load_commit` not read).
- Implicit: `vault_path`.

**Outputs & Effects:** Returns bytes or raises. `IsADirectoryError`/`PermissionError` propagate as themselves.

**Cross-Function Dependencies:** Callers (many): `Vault__Sub_Tree.checkout` L195 (catches `FileNotFoundError`, L196), `Vault__Sync__Base._checkout_flat_map` L519 (inside `except Exception: pass`), `Vault__Branch_Switch` L417, `Vault__Revert` L132, `Vault__Restore` L182, `Vault__Sync__Sparse` L129, `Vault__Merge` L98, `Vault__Bare._get_head_tree_id` L105, `verify_integrity` L139, `Vault__Sync__Tag._load_tag` L194.

**Open Questions:**
- Shape validation of `commit_id` as read back from a ref before it is used as a path component (see `Vault__Ref_Manager.read_ref`).
