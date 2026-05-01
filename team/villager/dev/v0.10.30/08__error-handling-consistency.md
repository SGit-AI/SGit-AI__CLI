# Finding 08 — Error-Handling Consistency

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** minor
**Owners:** Villager Dev

---

## Summary

The new sprint code is largely consistent in raising `RuntimeError`
with user-actionable messages. Two patterns warrant flagging.

## 8.1 — Bare `except Exception:` swallows real errors

`Vault__Sync.probe_token` (line 1817–1832) silently catches `Exception`
in two places:

```python
try:
    idx_data = self.api.batch_read(vault_id, [f'bare/indexes/{index_id}'])
    if idx_data.get(f'bare/indexes/{index_id}'):
        return dict(type='vault', vault_id=vault_id, token=token_str)
except Exception:
    pass
...
try:
    probe_at.info(vault_id)
    return dict(type='share', transfer_id=vault_id, token=token_str)
except Exception:
    pass

raise RuntimeError(
    f"Token not found on SGit-AI or SG/Send: '{token_str}'\n"
    ...
)
```

A 5xx, network timeout, or malformed-response from the server is
indistinguishable from "vault not found", because both lead to the same
final `RuntimeError`. The user message says "Token not found", which is
**inaccurate** when the failure was network / server.

**Recommendation:** narrow the exception class. Catch only the
specific "404 / not found" exception class from
`Vault__API`/`API__Transfer`, and let other errors propagate or wrap
them as `RuntimeError("probe failed: <reason>")`. Same pattern at
`_clone_resolve_simple_token` (line 1862, 1875).

## 8.2 — Push checkpoint silently re-starts on corrupted JSON

`Vault__Sync._load_push_state` (line 2729–2740):

```python
def _load_push_state(self, path: str, vault_id: str, clone_commit_id: str) -> dict:
    if os.path.isfile(path):
        try:
            with open(path, 'r') as f:
                state = json.load(f)
            if (state.get('vault_id') == vault_id and
                    state.get('clone_commit_id') == clone_commit_id):
                return state
        except Exception:
            pass
    return {'vault_id': vault_id, 'clone_commit_id': clone_commit_id, 'blobs_uploaded': []}
```

On corrupted JSON or version-mismatch, the function silently returns a
**fresh** state, meaning the user re-uploads every blob without warning.
The intended UX is "graceful continue", but a debug-log line or
`progress.warn()` callback is missing — the user has no observability
into the fact that their checkpoint was discarded.

**Recommendation:** at minimum, emit a `print(...)` to stderr or call
`debug_log` if available. Same pattern in `Token_Store.load_clone_mode`
(line 2287–2289 of `CLI__Vault.py` — fallback to empty dict on
corrupted JSON).

## 8.3 — `delete_on_remote` write-key check is correct, but message is weak

`Vault__Sync.py:1733`:

```python
raise RuntimeError('delete-on-remote requires write access — read-only clones cannot delete a vault')
```

This is fine, but the equivalent guard in `cmd_delete_on_remote`
(`CLI__Vault.py:965`) raises a slightly different message:

```python
raise RuntimeError('This is a read-only clone — cannot delete a vault without write access.')
```

Two messages for the same state. Pick one and either share the
message or inline it on the deepest layer. (The CLI layer guard is
arguably redundant — the sync layer would raise anyway.) Not a bug,
but a consistency smell.

## 8.4 — `rekey_commit` swallows `'nothing to commit'`

`Vault__Sync.py:1784`:

```python
try:
    result = self.commit(directory, message='rekey')
    return dict(commit_id=result['commit_id'],
                file_count=result.get('files_changed', 0))
except RuntimeError as e:
    if 'nothing to commit' in str(e).lower():
        return dict(commit_id=None, file_count=0)
    raise
```

String-matching on a `RuntimeError` message is brittle. If the message
is rephrased in `commit()` (e.g., "no changes detected") this branch
silently fails. Recommendation: a typed exception (`Vault__Empty_Tree`)
or a sentinel return from `commit()`. **Tagged
`do-not-refactor-without-tests-first`** — the test suite has no test
for the "rephrased message" failure mode.

## 8.5 — Read-only guard duplication across layers

`_check_read_only` exists at `CLI__Vault.py:263` (CLI layer) and the
same logic implicitly runs again at `Vault__Sync.delete_on_remote`
(line 1732 — `if not c.write_key`). Both are correct individually, but
two enforcement points means future changes have to be made in two
places. Suggested seam: a single sync-layer guard that both CLI and
direct-Python callers route through.

## 8.6 — `_check_read_only` swallows malformed clone_mode.json

`CLI__Vault.py:265–267`:

```python
clone_mode = self.token_store.load_clone_mode(directory)
if clone_mode.get('mode') == 'read-only':
    raise RuntimeError('This is a read-only clone. commit and push are not available.')
```

If `clone_mode.json` is malformed, `load_clone_mode` returns
`{'mode': 'full'}` (per `test_load_clone_mode_corrupted_file_returns_full`).
This means a corrupted clone_mode.json **silently downgrades the
vault to read-write**. For a security-sensitive guard this is a
**fail-open** posture. **Escalation: AppSec** — check whether the
read-only guard is intended to be authoritative or advisory. If
authoritative, malformed should fail-closed.

## Severity rationale

**minor** — no current bug because the existing code paths produce
acceptable user-visible behaviour. The hardening recommendations
above are quality-of-implementation issues, not blockers. Item 8.6
escalates to AppSec because the fail-open posture has security
implications.

## Suggested next-action

- **AppSec** — confirm fail-closed vs fail-open intent for 8.6.
- **Villager Dev** — fix 8.3 (consolidate message) once tests exist
  for the message text. Defer 8.1, 8.2, 8.4 to Phase 3.
