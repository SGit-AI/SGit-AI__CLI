## `refuse_bytes` in sgit_ai/core/Vault__Secret_Guard.py (L64-L73)

```python
# L65-L73
if not content.startswith(ZIP_MAGIC): return
entry = self._secret_entry(content)
if entry:
    raise Vault__Secret_In_Commit_Error(f'refusing to commit {rel_path}: it is a zip holding {entry} ...')
```

**Purpose:** Content check for an in-memory file: refuse when it is a zip holding a vault secret; the message names the entry and the `--allow-secret-file` override.

**Inputs & Assumptions:** `rel_path` (for the message, printed verbatim); `content` (bytes, whole file in memory — `read_regular` has already read it; file size is unbounded here). Trust: the file is the user's own working-copy content.

**Outputs & Effects:** Raises or returns; pure.

**Cross-Function Dependencies:** Callee `_secret_entry` L75. Callers: `refuse_files` L62; `Vault__Sync__Commit.write_file` L278 (the bytes `sgit write` is about to commit; no hard-link check applies since the content is in memory, and no `--allow-secret-file` override exists on that path).

**Open Questions:** none.
