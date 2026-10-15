## `is_store_path` in sgit_ai/storage/Vault__Verified_Write.py (L29-L37)

```python
# L34-L37
fid = '' if file_id is None else str(file_id)
if not STORE_FILE_ID.match(fid):
    return False
return not Vault__Path_Guard().is_protected(fid)
```

**Purpose:** Accept only ids naming a leaf of the bare store (docstring L30-L33). It is what keeps a host-chosen id such as `local/vault_key` or `local/config.json` out of `save`.

**Inputs & Assumptions:** `file_id` untrusted. The regex (L18-L19) is anchored with `^…$` — `$` in Python matches before a trailing newline, so `'bare/data/x\n'` matches; `safe_join` later keeps the newline in the filename (L141, original string) and `open` writes a file whose name ends in `\n`. Contained, but a distinct file from `bare/data/x`. `nothing found` that strips or rejects it.

**Outputs & Effects:** Pure bool.

**Cross-Function Dependencies:** Callee `Vault__Path_Guard.is_protected` (applied to the whole id: `bare/data/.git` or `bare/keys/GIT~1` would be refused — harmless). Callers: `save` L76 only.

**Open Questions:** the trailing-newline / odd-byte leaf names above (whether any host can produce them is a host-model question).
