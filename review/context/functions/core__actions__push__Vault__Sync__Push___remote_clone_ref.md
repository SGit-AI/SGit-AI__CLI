## `_remote_clone_ref` / `_remote_clone_head` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L582-L595)

**Purpose:** The server's copy of the **clone branch** ref: `(raw bytes, commit id)` or `(None, '')`. Branch-only pushes use the raw bytes as the compare-and-swap match and the commit id as the chain stop (L630-L641).

**Inputs & Assumptions:** `vault_id`, `clone_ref_id`, `read_key`.

**Outputs & Effects:** one `api.read` of `bare/refs/<clone_ref_id>`; decrypt + parse. **Any exception → `(None, '')`** (L590-L592): offline, 404 (absent), and an undecryptable ref all look like "server has none".

**Block-by-Block:**
```python
# L585-L592
try:
    data = self.api.read(vault_id, f'bare/refs/{clone_ref_id}')
    if data:
        return data, (json.loads(self.crypto.decrypt(read_key, data)).get('commit_id') or '')
except Exception: pass
return None, ''
```
- **Assumes:** the consequence of `(None, '')` is acceptable in every case: `_push_branch_only` then writes the clone ref as a **plain write** (`expected_ref_hash=None` → `build_push_operations` L101-L104) and uses the local named head as the stop. For a genuinely absent ref that is the intended first write (TM-R33 shape); for an **offline or erroring** read the same plain write happens — contrast `_named_ref_absent_on_server` (L901-L914), which for the named ref treats "unknown" as "keep the CAS". `nothing found` distinguishing error from absence here.
- **Assumes:** the ref ciphertext is the clone ref's (TM-R03: not bound to its id).

`_remote_clone_head` (L594-L595) returns the commit id only.

**Cross-Function Dependencies:** callee `Vault__API.read`. Callers: `_push_branch_only` L630. `_remote_clone_head` has no callers (grep).

**Open Questions:**
- unclear; whether a branch-only push over a flaky connection overwriting the server's clone ref (own branch, not shared with teammates) is considered acceptable — the clone branch is this clone's alone by design, which may be why the distinction was not drawn.
