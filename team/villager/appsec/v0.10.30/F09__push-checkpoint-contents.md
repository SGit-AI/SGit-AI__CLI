# F09 — Resumable Push Checkpoint (`push_state.json`) Contents

**Severity:** LOW — verified clean
**Class:** Local-disk leak (potential)
**Disposition:** OK + TEST GAP
**Files:** `sgit_ai/sync/Vault__Sync.py:963-1068, 2729-2748`,
`sgit_ai/sync/Vault__Storage.py:86-87`

## 1. Schema (Verified by Code)

```python
# Vault__Sync.py:2740
return {'vault_id': vault_id, 'clone_commit_id': clone_commit_id,
        'blobs_uploaded': []}
```

Save (line 2742-2744):

```python
def _save_push_state(self, path: str, state: dict) -> None:
    with open(path, 'w') as f:
        json.dump(state, f)
```

The state dict only ever has three top-level fields:
- `vault_id` — server-known opaque hash, public.
- `clone_commit_id` — `obj-cas-imm-{...}`, public.
- `blobs_uploaded` — list of blob_ids, all public.

**No plaintext path, no plaintext filename, no read_key, no write_key, no
size, no content_hash.** Verified by reading every `push_state['blobs_uploaded'].append(...)`
call site (lines 990, 1014). Each `append` adds a string `bid` that is
`obj-cas-imm-{sha256(ciphertext)[:12]}`.

## 2. Lifecycle

- Created on resume (line 964): `_load_push_state` returns existing or new.
- Updated on each blob-upload success (line 990, 1014, 1016).
- Cleared on Phase-B success (line 1068): `self._clear_push_state(state_path)`.
- **Reset on context mismatch:** if `state.get('vault_id') != vault_id` or
  `clone_commit_id` differs, the loader returns a fresh dict (line 2735-2740)
  — preventing stale checkpoints from poisoning a different push.

## 3. CAS-Conflict Path

If `write-if-match` returns 409, `batch.execute_batch` raises and falls
through to `execute_individually` (line 1058-1060). The push_state is **not
cleared** in this path — by design, so a retry can resume. **No new
sensitive data accumulates** because only blob_ids are appended.

## 4. File Permissions

Same as F07: default umask, typically `0644`. Even though contents are
all public/opaque, world-readable file mode for `.sg_vault/local/*.json`
is bad hygiene. **Bundle with the F07 chmod recommendation.**

## 5. Test Coverage

I searched for tests asserting checkpoint structure:
- `test_Vault__Sync__Push.py` — does not introspect `push_state.json`.
- No test in `tests/unit/sync/` opens and validates the file contents.

**Mutation M8 (planned):** add `'paths': flat_map` to the saved checkpoint —
this would dump plaintext paths to disk. **Current test suite would NOT
catch this mutation.** The `dict.update()` from a future refactor could
silently leak.

**Test to add (small, high-value):**

```python
def test_push_state_contains_only_safe_fields(env, sync):
    # interrupt push mid-way, inspect file
    state_path = Vault__Storage().push_state_path(env.vault_dir)
    with open(state_path) as f: s = json.load(f)
    assert set(s.keys()) <= {'vault_id', 'clone_commit_id', 'blobs_uploaded'}
    for bid in s['blobs_uploaded']:
        assert bid.startswith('obj-cas-imm-')
```

## 6. Disposition

- **Verified clean** today.
- **Test gap (M8):** add the schema-allowlist test above.
- **Hygiene fix:** chmod 0600 on save.
- **No code change needed** beyond hygiene.
