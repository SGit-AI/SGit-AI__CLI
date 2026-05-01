# Finding 10 — State-File Schemas (`clone_mode.json`, `push_state.json`)

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** minor (Type_Safe drift), but blocking for any future
schema-evolution work
**Owners:** Architect (boundary call), Villager Dev (mechanical
introduction once Architect approves)

---

## Summary

Two new persisted JSON files were added this sprint, both written and
read as **raw `dict`** with **no `Schema__*` class** to enforce shape:

- `.sg_vault/local/clone_mode.json` — sprint-introduced (commit
  `7c5d2f7`).
- `.sg_vault/local/push_state.json` — sprint-introduced (commit
  `ca50dfd`).

Each violates CLAUDE.md §6 "Round-trip invariant: every schema must
pass `assert cls.from_json(obj.json()).json() == obj.json()`" because
there is no schema to round-trip-test.

## clone_mode.json

**Shape (observed in code):**

```json
{ "mode": "read-only" | "full",
  "vault_id": "<vault_id>",
  "read_key": "<hex>" }
```

**Producers:** `CLI__Vault.py:1550`, `CLI__Vault.py:1654` (two
duplicate writers — see finding 5.2).

**Consumers:** `CLI__Token_Store.load_clone_mode`,
`CLI__Vault._check_read_only`, `CLI__Vault.py:2278–2289` (inline read
with try/except + empty-dict fallback).

**Suggested schema:**

```python
class Schema__Clone_Mode(Type_Safe):
    mode      : Safe_Str__Clone_Mode = None   # 'full' | 'read-only'
    vault_id  : Safe_Str__Vault_Id   = None
    read_key  : Safe_Str__Encrypted_Value = None
```

(Or an `Enum__Clone_Mode` for `mode`.)

## push_state.json

**Shape (observed in `Vault__Sync._load_push_state` and call sites):**

```json
{ "vault_id":         "<vault_id>",
  "clone_commit_id":  "<commit_id>",
  "blobs_uploaded":   ["<blob_id>", "<blob_id>", ...] }
```

**Producers / Consumers:** `Vault__Sync._load_push_state`,
`_save_push_state`, `_clear_push_state` (lines 2729–2748);
`push()` reads/writes during the upload loop (lines 963–1068).

**Suggested schema:**

```python
class Schema__Push_State(Type_Safe):
    vault_id        : Safe_Str__Vault_Id   = None
    clone_commit_id : Safe_Str__Object_Id  = None
    blobs_uploaded  : list[Safe_Str__Object_Id]
```

## Why a schema matters

1. **Round-trip invariant** — without a schema there is no contract
   for serialisation. Adding a field anywhere in
   `_load_push_state` requires manual coordination at the read site.
2. **Field naming drift** — `read_key` here is hex; `read_key` in
   `Vault__Components` is bytes; `read_key` in
   `Vault__Crypto.import_read_key` returns hex. Without a schema, type
   confusion is silent.
3. **Forward-compat** — when `clone_mode.json` grows a new field
   (e.g., the recently mentioned `'full'` mode with structure-only
   download), the pickle of the existing field set is fragile. A
   Schema with `default=None` for added fields makes this explicit.
4. **Test coverage** — Schema classes are auto-tested by the existing
   `test_Schema__*.py` pattern (`tests/unit/schemas/`). Currently no
   test asserts the JSON shape of these two files.

## Schema introduction is **safe** (Villager Dev scope)

Unlike the `Vault__Sync` return-shape refactor (finding 01), introducing
two new schemas does **not** change any public Python contract:

- The schemas wrap an already-persisted JSON shape.
- Existing dict-based call sites can be changed in lock-step without
  affecting external consumers.
- All writers funnel through `Vault__Storage` paths; the schema can
  be invoked at the I/O boundary only.

This is a Villager Dev-style "harden" task once Architect signs off
on the new schema names + Safe_* type choices.

## Behaviour to preserve (no-change envelope)

- Corrupted `clone_mode.json` must still fall back to `{'mode': 'full'}`
  — see `Token_Store.load_clone_mode` test
  `test_load_clone_mode_corrupted_file_returns_full`.
- Push-state with mismatched `vault_id` or `clone_commit_id` must still
  reset to a fresh state (line 2735–2740).
- Push-state file is unconditionally rewritten after each blob upload.
  Schema introduction must keep this fsync-friendly write pattern.

## Severity rationale

**minor** — no current bug. Becomes major if either file grows new
fields without Schema enforcement, or if AppSec confirms the
"corrupted-clone_mode → full mode fallback" is a security concern
(see finding 8.6).

## Suggested next-action

- **Architect** — pick schema names: `Schema__Clone_Mode`,
  `Schema__Push_State`. Pick `Enum__Clone_Mode` vs free-form
  `Safe_Str__Clone_Mode`. Pick `list[Safe_Str__Object_Id]` vs a richer
  per-blob entry shape (the latter would let a future change track
  upload size / timestamp per blob).
- **Villager Dev** — once names are picked, introduce the schemas
  and rewire the 4 call sites (2 writers, 2 readers for clone_mode;
  3 helpers for push_state). Add round-trip tests under
  `tests/unit/schemas/`.
