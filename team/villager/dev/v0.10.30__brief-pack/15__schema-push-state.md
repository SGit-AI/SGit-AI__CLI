# Brief 15 — Schema: `Schema__Push_State` for push_state.json

**Owner role:** **Villager Architect** (design + naming) + **Villager Dev** (implementation)
**Status:** Ready to execute. Recommended after brief 14 lands.
**Prerequisites:** Brief 14 strongly preferred (the bug fix tests
already exercise the push_state shape).
**Estimated effort:** ~2 hours
**Touches:** new schema in `sgit_ai/schemas/`, callers in
`sgit_ai/sync/Vault__Sync.py`, tests under `tests/unit/schemas/` and
`tests/unit/sync/`.

---

## Why this brief exists

Architect finding 05 + Dev finding 10 + AppSec mutation matrix M8: the
on-disk `push_state.json` file has no Type_Safe schema. It is
read/written as a raw dict in `_load_push_state` / `_save_push_state`,
violating CLAUDE.md rule 1 ("Zero raw primitives in Type_Safe classes")
in spirit, and leaving the AppSec mutation gap M8 (server-side or
attacker injection of an extra field) open at the read site.

The fix: introduce `Schema__Push_State` (Type_Safe class), use it in
both load and save paths. The round-trip invariant `from_json(obj.json()).json()
== obj.json()` then closes M8 structurally — any unexpected field on
read raises during validation rather than being silently honoured.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/05__type-safe-hygiene-on-additions.md`.
3. `team/villager/dev/v0.10.30/10__state-files-schema.md`.
4. `team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md` row M8.
5. `CLAUDE.md` Type_Safe rules (especially Safe_* type pattern + schema pattern + round-trip invariant).
6. `sgit_ai/schemas/` for naming conventions and existing patterns.
7. `sgit_ai/sync/Vault__Sync.py` `_load_push_state` and `_save_push_state`
   methods (~line 2729–2748 per Dev finding 09) — read to understand
   the current dict shape.

---

## Scope

**In scope:**
- Define `Schema__Push_State` with the fields actually written today.
  Use Safe_* types throughout (not raw `str`/`int`/`dict`). Cite the
  source code so the field set is grounded.
- Define any nested Safe_* / Schema__* types needed for nested fields
  (e.g., a `Schema__Push_Phase_A_State` if there's nested structure).
- Refactor `_load_push_state` and `_save_push_state` to use the schema:
  - On save: `Schema__Push_State` instance → `.json()` → file.
  - On load: read file → `Schema__Push_State.from_json(...)` →
    instance.
- Round-trip invariant test:
  `assert Schema__Push_State.from_json(obj.json()).json() == obj.json()`.
- Mutation matrix M8 closer test: a maliciously injected extra field
  in `push_state.json` must cause load to fail with a typed error.

**Out of scope:**
- Migration of existing `push_state.json` files. The push state is
  ephemeral (deleted on push completion); no migration is needed —
  document this assumption.
- Changing the resumable-push protocol.
- Schema for `clone_mode.json` — brief 16.

**Hard rules:**
- Strict Type_Safe: no `dict`, `str`, `int` raw fields.
- Naming: `Schema__Push_State`, Safe types `Safe_*__*` per CLAUDE.md.
- Round-trip invariant test mandatory.
- No new mocks.

---

## Acceptance criteria

- [ ] `Schema__Push_State` exists in `sgit_ai/schemas/` with proper
      naming and Safe_* fields.
- [ ] `_load_push_state` and `_save_push_state` use the schema.
- [ ] Round-trip invariant test passes.
- [ ] M8 closer test exists and passes (extra-field injection rejected).
- [ ] Mutation matrix M8 row updated to "D" (detected).
- [ ] Suite ≥ 2,105 passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] No raw primitives in the schema.

---

## Deliverables

1. New schema source file under `sgit_ai/schemas/`.
2. Refactored `_load_push_state` / `_save_push_state`.
3. Test file under `tests/unit/schemas/test_Schema__Push_State.py`.
4. Mutation matrix M8 update.
5. Closeout entry on `team/villager/architect/v0.10.30/05__type-safe-hygiene-on-additions.md`.

Commit message:
```
refactor: Schema__Push_State for push_state.json

Closes Architect finding 05 + Dev finding 10. push_state.json was
read/written as a raw dict; now backed by Schema__Push_State
(Type_Safe). Round-trip invariant + extra-field rejection close
AppSec mutation gap M8 structurally.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Schema field list + Safe_* types used.
2. Test count + the M8 closure mechanism.
3. Coverage delta on `_load_push_state` / `_save_push_state` (likely
   100%).
