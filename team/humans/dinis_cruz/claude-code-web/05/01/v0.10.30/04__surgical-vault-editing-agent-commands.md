# Debrief 04: Surgical Vault Editing — Agent Support Commands

**Commits:** `7c5d2f7`, `61b79fd`  
**Date:** April 27, 2026  
**Files changed:** `Vault__Sync.py`, `CLI__Vault.py`, `CLI__Main.py`, `Vault__Storage.py`, `Vault__Crypto.py`

---

## Problem

Agents using sgit-ai as a vault backend needed to write individual files without:
1. Scanning the entire working directory (slow for large vaults)
2. Decrypting and re-encrypting existing content (requires only the change)
3. Waiting for full clone infrastructure to be set up

Similarly, inspection commands (`cat`, `ls`) returned human-readable text only — machine-readable JSON output was needed for agent pipelines.

---

## New Command: `sgit write`

### Behavior

Writes file content directly to the vault HEAD without scanning the working directory. The operation is:

1. Load the current HEAD commit → get old flat map via `flatten()`
2. Compute content hash of the new content
3. If content hash matches existing entry → return existing blob_id, no new commit
4. Encrypt the blob → store in object store
5. Update the flat map with the new entry
6. Build tree from updated flat map → create commit → update ref
7. Write file to working copy on disk
8. Return `blob_id` (stdout) + optionally push

### Flags

```
sgit write <vault_path> <local_file>     write from local file
sgit write <vault_path> -                read stdin
--also VAULT_PATH:LOCAL_FILE             atomic multi-file commit
--push                                   push immediately after write
--message "msg"                          custom commit message
--json                                   structured output {blob_id, commit_id, ...}
```

### `--also` for Atomic Multi-File Commits

Multiple files can be committed in a single operation:
```bash
sgit write config/prod.yaml ./prod.yaml \
     --also secrets/api.key:./api.key \
     --also README.md:./README.md \
     --push
```

All files are updated in one commit. If any file is unchanged (content hash matches), it's silently skipped but the commit is still created for the changed files.

### Content-Hash Deduplication

The same optimization used in `commit()` is applied: if the SHA-256 of the new content matches the stored `content_hash` for the path, the existing blob_id is reused and no new commit is created. Return value has `unchanged: True`.

### Read-Only Guard

Write is blocked on read-only clones (clones created from a share token with no write key). The guard checks `clone_mode.json` for `edit_token` before any crypto work.

### Implementation: `Vault__Sync.write_file()`

```python
def write_file(self, directory, path, content, message='', also=None, push=False):
    # load HEAD flat map
    old_flat = sub_tree.flatten(old_commit.tree_id, read_key) if parent_id else {}
    flat = dict(old_flat)
    
    # handle content-hash dedup
    for file_path, file_content in files_to_write.items():
        file_hash = self.crypto.content_hash(file_content)
        old_entry = flat.get(file_path)
        if old_entry and old_entry.get('content_hash') == file_hash:
            blob_id = old_entry['blob_id']   # reuse, no new commit
        else:
            encrypted = self.crypto.encrypt(read_key, file_content)
            blob_id   = obj_store.store(encrypted)
            any_changed = True
        flat[file_path] = {blob_id, size, content_hash, content_type, large}
    
    if not any_changed and not new_paths:
        return {unchanged: True, blob_id: ..., commit_id: parent_id}
    
    root_tree_id = sub_tree.build_from_flat(flat, read_key)
    commit_id    = vault_commit.create_commit(tree_id=root_tree_id, ...)
    ref_manager.write_ref(ref_id, commit_id, read_key)
    # write file to disk
    return {blob_id, commit_id, message, paths, unchanged: False}
```

---

## Extensions to `sgit cat`

### `--id` flag
Prints only the blob_id without downloading the blob content. The blob_id is read from tree metadata (`flatten()` only — zero object downloads).

```bash
$ sgit cat docs/report.pdf --id
obj-cas-imm-3a9f2b8e1c4d
```

Useful for checking whether a file has changed between commits without fetching it.

### `--json` flag
Outputs structured metadata:
```json
{
  "path": "docs/report.pdf",
  "blob_id": "obj-cas-imm-3a9f2b8e1c4d",
  "size": 142387,
  "content_type": "application/pdf",
  "fetched": true
}
```

`fetched: true` means the blob was already in the local object store; `false` means it was fetched from the server for this call.

---

## Extensions to `sgit ls`

### `--ids` flag
Adds a blob_id column to the existing tabular output.

### `--json` flag
Outputs the full entry array as JSON, one object per file:
```json
[
  {
    "path": "src/main.py",
    "blob_id": "obj-cas-imm-8c1d4092f7a3",
    "size": 4200,
    "content_type": "text/x-python",
    "large": false,
    "local": true
  }
]
```

---

## `Vault__Crypto.import_read_key()`

New method that reconstructs the full key bundle from a read_key hex string and vault_id — without the passphrase. This lets read-only access (share token clones) still derive ref IDs and branch index IDs needed for inspection commands.

```python
def import_read_key(self, read_key_hex: str, vault_id: str) -> dict:
    read_key_bytes       = bytes.fromhex(read_key_hex)
    ref_file_id          = 'ref-pid-muw-' + self.derive_ref_file_id(read_key_bytes, vault_id)
    branch_index_file_id = 'idx-pid-muw-' + self.derive_branch_index_file_id(read_key_bytes, vault_id)
    return dict(read_key_bytes=read_key_bytes, write_key='', write_key_bytes=None, ...)
```

---

## Design Principle: Minimal Surface Area

`write_file()` operates entirely on the flat map representation — it never re-reads the working directory, never scans subdirectories, and touches only the single file being written. This keeps it fast for agents that:
- Have generated content in memory (no disk I/O until the write completes)
- Are writing to sparse clones (no blobs downloaded)
- Are running in tight execution time budgets
