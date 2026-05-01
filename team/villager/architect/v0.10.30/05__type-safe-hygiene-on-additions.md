# Finding 05 — Type_Safe hygiene on sprint additions

**Verdict:** `BOUNDARY DRIFT` — three Type_Safe rule violations introduced
or worsened during the sprint. None of them are SEND-BACK-TO-EXPLORER, but
all three should be cleaned up before the next Explorer wave.

---

## 1. `Schema__Local_Config` no longer matches the file it represents (HIGH)

`sgit_ai/schemas/Schema__Local_Config.py`:

```python
class Schema__Local_Config(Type_Safe):
    my_branch_id : Safe_Str__Branch_Id = None
```

The actual file at `.sg_vault/local/config.json` is now written with up to
four extra fields, none declared on the schema:

| Field | Type | Writer | Reader |
|---|---|---|---|
| `my_branch_id` | `Safe_Str__Branch_Id` | `_clone_with_keys` line 1442 | `_read_local_config` line 1882 (round-trip) |
| `mode` | `str` (literal `'simple_token'`) | line 1445 | inferred elsewhere |
| `edit_token` | `str` (raw) | line 1446 | grep shows uses in `_check_read_only` chain |
| `sparse` | `bool` (raw) | line 1448 | line 458, line 662 — both via raw `.get('sparse')` |

The reader at line 1882 does
`Schema__Local_Config.from_json(data)` — which means **the extra fields are
silently dropped on deserialisation through the schema**, but the writer puts
them in via a raw dict. The implementation pattern is:

```python
local_config_data = dict(Schema__Local_Config(...).json())   # schema-controlled
if sparse: local_config_data['sparse'] = True                # bypasses schema
```

This is a Type_Safe rule violation. The schema is not the contract — the
implementation is. Two negative consequences:

1. **Round-trip invariant fails** for any config that has `sparse: true`
   written. `Schema__Local_Config.from_json(d).json() != d`.
2. **The status code at line 458** reads `sparse` from the parsed JSON
   directly (`json.load(_cf).get('sparse')`) — not via the schema. So the
   schema is NOT what tells the rest of the codebase about sparse state.

Recommended: either (a) extend `Schema__Local_Config` with `mode`,
`edit_token`, `sparse` fields (preferred), or (b) introduce a
`Schema__Local_Config__V2` that owns the additions and route everything
through it. Either way, `local_config.json` becomes a properly typed
artefact.

## 2. `push_state.json` has no schema at all (MEDIUM)

`Vault__Sync._load_push_state`, `_save_push_state` (lines 2729–2748) read
and write a free-form dict with three keys (`vault_id`, `clone_commit_id`,
`blobs_uploaded`). No `Schema__Push_State` class exists.

Rule 1 of `CLAUDE.md` says "Zero raw primitives in Type_Safe classes" — the
sprint introduces a new on-disk artefact that bypasses Type_Safe entirely.

Recommended:

```python
class Schema__Push_State(Type_Safe):
    vault_id        : Safe_Str__Vault_Id  = None
    clone_commit_id : Safe_Str__Object_Id = None
    blobs_uploaded  : list[Safe_Str__Object_Id]
```

(Verifying the `list[Safe_Str__Object_Id]` type — `Safe_Str__Object_Id`
exists per `safe_types/`. Round-trip invariant should be added in a test.)

## 3. `clone_mode.json` has no schema either (MEDIUM)

Same problem as `push_state.json`. The file holds three keys (`mode`,
`vault_id`, `read_key`) but is read/written via raw dict in
`Vault__Sync._init_components` (line 2283) and `clone_read_only`
(lines 1550–1552, 1654–1656).

Recommended `Schema__Clone_Mode`:

```python
class Schema__Clone_Mode(Type_Safe):
    mode     : Safe_Str__Clone_Mode = None       # 'read-only' | 'full' | 'sparse' (?)
    vault_id : Safe_Str__Vault_Id   = None
    read_key : Safe_Str__Hex_Bytes  = None
```

Open question: should `mode='sparse'` live here or in `local_config.json`?
The sprint chose `local_config.json` for sparse and `clone_mode.json` for
read-only — that's a *fragile* split (debrief 01 mistakenly merged them).
Architect/Sherpa decision needed.

## 4. New methods returning raw dicts

Most of `Vault__Sync`'s public surface returns dicts. The sprint additions
follow that pattern:
- `probe_token` returns `{type, vault_id, token}` or `{type, transfer_id, token}`.
- `delete_on_remote` returns `{status, vault_id, files_deleted}`.
- `rekey_check` returns `{vault_id, file_count, obj_count, clean}`.
- `rekey` returns `{vault_key, vault_id, commit_id}`.
- `write_file` returns `{blob_id, commit_id, message, paths, unchanged}`.
- `sparse_fetch` returns `{fetched, already_local, written}`.

This is consistent with the pre-existing patterns (`commit`, `pull`, `push`,
`status` all return dicts). Whether to convert all of them to schemas is a
larger architectural decision. The sprint did NOT make it worse — it just
didn't make it better either.

**Out of scope for v0.10.30 cleanup.** Flag for a Phase 4 strategic decision.

## 5. Naming — clean

Reviewed all sprint additions:
- `probe_token`, `delete_on_remote`, `rekey*`, `write_file`, `sparse_*`,
  `_clone_download_blobs`, `_fetch_missing_objects` — all snake_case method
  names on `Vault__Sync`.
- `Vault__Storage.find_vault_root`, `push_state_path`, `clone_mode_path` —
  consistent with surrounding methods.
- New `Vault__Crypto.import_read_key`, `encrypt_deterministic`,
  `encrypt_metadata_deterministic` — consistent with existing names.

No new `Schema__*` or `Safe_Str__*` were added in the sprint, so naming on
those is unaffected.

## 6. No raw primitives introduced in NEW Type_Safe classes

Spot-checked the diff for new `Type_Safe` subclass declarations. The sprint
adds **no new Type_Safe classes**. It only adds methods to existing ones
(`Vault__Sync`, `Vault__Crypto`, `Vault__Storage`, `Vault__Sub_Tree`,
`CLI__Vault`). So the "no raw primitives in Type_Safe fields" rule is
trivially upheld for additions.

The violation is in the implementation: two new on-disk JSON artefacts
(`push_state.json`, sparse-flagged `local_config.json`) skip Type_Safe
entirely.

## 7. Immutable defaults — clean

Spot-checked all new method bodies for mutable default args:

```python
def write_file(self, ..., also: dict = None) -> dict:
def reset(self, directory: str, commit_id: str = None) -> dict:
def clone(self, ..., on_progress: callable = None, sparse: bool = False) -> dict:
def probe_token(self, token_str: str) -> dict:
```

All defaults are `None`, `False`, `''` — immutable. Rule upheld.

## 8. Hand-off

- **Dev (Phase 3 priority):** add `Schema__Push_State`, `Schema__Clone_Mode`,
  extend `Schema__Local_Config` with the four undeclared fields.
- **Sherpa/Architect (joint):** decide whether `mode=sparse` belongs in
  `clone_mode.json` or `local_config.json`. Today it's in `local_config.json`,
  but the file naming suggests it should be in `clone_mode.json`.
- **QA:** add round-trip tests for the three schemas above.
