# Finding 05 — Duplication Across New Commands

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** minor
**Owners:** Architect (boundary call), Villager Dev (mechanical extract
once Architect approves)

---

## Summary

Five duplication patterns appeared or grew during this sprint. None
of them is a behaviour bug — they are code-smell candidates for a
future Phase 3 extraction.

## 5.1 — `derive_keys_from_simple_token` + `batch_read('bare/indexes/...')`

The exact same 6-line "derive vault_id and index_id from a simple
token, then `batch_read` the index" pattern is repeated:

| Location | Lines |
|----------|------:|
| `Vault__Sync.probe_token` | 1813–1820 |
| `Vault__Sync._clone_resolve_simple_token` | 1854–1861 |
| `Vault__Sync.init` (was already there pre-sprint) | ~80 |

```python
keys      = self.crypto.derive_keys_from_simple_token(token_str)
vault_id  = keys['vault_id']
index_id  = keys['branch_index_file_id']
idx_data  = self.api.batch_read(vault_id, [f'bare/indexes/{index_id}'])
if idx_data.get(f'bare/indexes/{index_id}'):
    ...
```

**Risk:** if probe and clone diverge on edge cases (e.g., empty
batch_read response, malformed index, transient 5xx), the two callers
will silently disagree on whether a token resolves to a vault.
Tagged: `do-not-refactor-without-tests-first`.

**Suggested seam:** a private helper `_probe_index(token_str) -> dict`
returning `{'found': bool, 'vault_id': str, 'index_id': str}`.

## 5.2 — `clone_mode.json` write/read scattering

```python
clone_mode = dict(mode='read-only', vault_id=vault_id, read_key=read_key_hex)
with open(storage.clone_mode_path(directory), 'w') as f:
    _json.dump(clone_mode, f, indent=2)
```

This block appears verbatim at:

- `sgit_ai/cli/CLI__Vault.py:1550–1552`
- `sgit_ai/cli/CLI__Vault.py:1654–1656`

And the corresponding read happens in three places:

- `sgit_ai/cli/CLI__Vault.py:2278–2289` (inline, with try/except + empty-dict fallback)
- `sgit_ai/cli/CLI__Token_Store.py` (`load_clone_mode`)
- `sgit_ai/cli/CLI__Vault.py:_check_read_only` (line 263–267, calls `token_store.load_clone_mode`)

The reader on `Token_Store` correctly funnels reads through one
method; the writer is duplicated. Recommendation:
`Vault__Storage.save_clone_mode(directory, clone_mode_dict)` — or
better, `save_clone_mode(directory, mode: Schema__Clone_Mode)`.
See finding 10 for the Schema proposal.

## 5.3 — `branch_index_file_id` guard repeated 7+ times

Pattern appears at lines 168, 247, 356, 414, 602, 837, 1174 of
`Vault__Sync.py` (and possibly more):

```python
index_id = c.branch_index_file_id
if not index_id:
    raise RuntimeError('No branch index found — is this a v2 vault?')
branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
```

This is pre-existing duplication, not sprint-introduced — the
sprint only added one new instance (at line 247 in `write_file`).
Mention here for completeness. Suggested seam:
`c._require_branch_index(branch_manager, read_key) -> Schema__Branch_Index`.

## 5.4 — Push checkpoint state I/O

`_load_push_state`, `_save_push_state`, `_clear_push_state` at
`Vault__Sync.py:2729–2748`:

- All three pass a raw `state: dict`.
- `_load_push_state` catches `Exception` and silently returns a fresh
  state — this hides JSON-corruption from the user (already
  problematic; see finding 08).
- `clone_mode.json` follows the same "if json fails, default to
  empty/full" pattern (line 2287, `Token_Store.load_clone_mode`).

The two state files (`push_state.json` and `clone_mode.json`) repeat
the same load/save/clear/corruption-tolerant idiom. A single helper
`_load_state_file(path, default)` and `_save_state_file(path, state)`
would consolidate both. **Schema-typed** versions are even better
(finding 10).

## 5.5 — Rekey is `wipe → init → commit`

`Vault__Sync.rekey()` at line 1789 is a 4-line wrapper that calls
`rekey_wipe`, `rekey_init`, `rekey_commit` and packs the dict. Each
sub-step is also exposed as its own public method and own CLI
sub-command (`sgit rekey wipe`, `sgit rekey init`, `sgit rekey
commit`). This is **intentional**, not duplication, and is well-tested.
No action — listed for completeness because it is the pattern that
makes the rekey wizard auditable.

## What this means for the v0.5.11 baseline

v0.5.11's deep audit flagged `Vault__Sync.py` as the largest source
of cross-cutting duplication (token-handling, ref-handling). This
sprint **did not reduce** that duplication and added two new
instances (5.1 and 5.4). Net direction: slightly worse.

## Severity rationale

**minor** — no behaviour bug. All extractions are mechanical and
should be done as a Phase 3 refactor with tests in place.

## Suggested next-action owner

- **Architect** — boundary call: should the duplication patterns
  above warrant a `Vault__State_Files` helper class (clone_mode,
  push_state, tracking, remotes) plus a `Vault__Token_Resolver`
  helper class (probe + simple-token resolution)? Both have natural
  seams. Villager Dev does not split. Architect decision required.
- **Villager Dev** — once Architect approves, perform the extractions
  with a "no behaviour change" diff (existing tests + rationale tests).

## Out of scope

- `_clone_with_keys` vs `clone_read_only` vs `clone_from_transfer`
  — three separate clone paths that share ~40% of their bodies. This
  is well-known pre-sprint duplication. Not flagged here.
