# Brief B10 — Vault Migration Command

**Owner role:** **Villager Dev** (Architect-blessed for migration-step list)
**Status:** BLOCKED until brief B08 lands.
**Prerequisites:** B08 (server packs) merged.
**Estimated effort:** ~2–3 days
**Touches:** new `Workflow__Migrate_Vault`, step classes, `sgit vault migrate` command, tests.

---

## Why this brief exists

Per decision 3: vault-format changes are allowed; newer vaults may
require newer binaries; **provide a migration command** following the
rekey precedent.

Several v0.11.x changes introduce optional new on-disk shapes that
benefit from migration:

- Server-side: precomputed packs (B08). Old vaults serve per-object;
  migration triggers pack pre-build server-side.
- Client-side: `.sg_vault/work/` is additive (created on first use); no
  migration needed.
- Future: any new schema for `clone_mode.json`, `push_state.json`,
  `local_config.json` (already addressed in v0.10.30 deferred briefs).

This brief ships the migration scaffolding so future format additions
have a tested path.

---

## Required reading

1. This brief.
2. `design__01__access-modes.md` (the modes).
3. `design__04__workflow-framework.md` (use the framework for migration too).
4. `design__05__clone-pack-format.md` (what server-side migration triggers).
5. The existing `sgit rekey` implementation — naming + UX precedent.

---

## Scope

### Step 1 — Command surface

Add to the new top-level: `sgit vault migrate <…>` (per `design__02` namespace).

Subcommands:
- `sgit vault migrate plan` — preview what would change (read-only).
- `sgit vault migrate apply` — execute the migration.
- `sgit vault migrate status` — what migrations have been applied to this vault.

### Step 2 — Migration framework

Each migration is a `Workflow__Migrate_*` composing migration steps.
Each migration is **versioned** and **idempotent** (re-running has no
effect if already applied).

```python
class Migration(Type_Safe):
    name        : Safe_Str__Migration_Name
    from_version: Safe_Str__Semver
    to_version  : Safe_Str__Semver
    steps       : list[type[Step]]

    def is_applied(self, vault) -> bool:
        ...
```

Applied-migration list lives at `.sg_vault/local/migrations.json`
(Type_Safe schema: `Schema__Migrations_Applied`).

### Step 3 — First migration: server pack pre-build

Migration `Migration__Server_Pack_Prebuild`:
1. Detect server pack support (probe endpoint).
2. Trigger server-side pack build for current HEAD (`POST /vaults/.../packs/build` — coordinate with B08 for the trigger endpoint).
3. Verify packs landed.
4. Record migration as applied.

This migration does NOT change the vault format on disk; it just
triggers server-side preparation. But it's a useful first migration to
validate the framework.

### Step 4 — Future migration slots (just register, no impl)

Register placeholder migration entries (with no-op steps + clear
"not-yet-implemented" markers) for foreseeable future migrations:
- `Migration__Schema_Push_State` (when v0.10.30 brief 15 lands)
- `Migration__Schema_Clone_Mode` (when v0.10.30 brief 16 lands)
- `Migration__Schema_Local_Config_Extension` (when v0.10.30 brief 17 lands)
- `Migration__Pack_Format_v2` (placeholder for any future pack-format bump)

These are just stubs so the migration registry is complete and
discoverable via `sgit vault migrate plan`.

### Step 5 — Tests

- `Migration` Type_Safe round-trip tests.
- `Schema__Migrations_Applied` round-trip tests.
- End-to-end: vault → `migrate plan` → `migrate apply` → `migrate status` shows it applied → re-running `migrate apply` is a no-op.
- Fail-on-mid-migration test: simulate a step failure; verify migration is NOT marked applied; resume works.
- The pack pre-build migration: verify server-side packs exist after apply.

---

## Hard constraints

- **Type_Safe everywhere.** Migration registry, applied-migrations list, every step.
- **Idempotent.** Every migration can be re-run safely.
- **Reversible where feasible.** Migrations should record undo info; bare-minimum is rollback to "not-applied" state on failure.
- **No mocks.** Real server fixture for pack pre-build test.
- **No `__init__.py` under `tests/`.**
- Coverage on new migration code ≥ 85%.
- Suite must pass under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] `sgit vault migrate <plan|apply|status>` commands work.
- [ ] At least one real migration (`Migration__Server_Pack_Prebuild`) ships and works against the in-memory server fixture.
- [ ] Migration registry contains stubs for the 4 foreseeable future migrations.
- [ ] Round-trip invariants pass for all schemas.
- [ ] At least 6 tests (round-trip × 2 + lifecycle × 4).
- [ ] Coverage on new migration code ≥ 85%.
- [ ] Suite ≥ existing test count + N passing.

---

## Out of scope

- Implementing the v0.10.30 schema migrations themselves — those are
  in v0.10.30 briefs 15/16/17. This brief just registers the slots.
- Cross-machine migration coordination (e.g., notifying other clones
  of the same vault that they need to migrate). Future work.
- Migration UI / progress bars beyond basic stdout.

---

## Deliverables

1. `sgit_ai/migrations/` package with `Migration`, `Workflow__Migrate_*`, registry.
2. `Schema__Migrations_Applied`.
3. `sgit vault migrate <…>` CLI.
4. `Migration__Server_Pack_Prebuild` first real migration.
5. Stubs for the 4 foreseeable future migrations.
6. Tests.

---

## When done

Return a ≤ 250-word summary:
1. Command surface confirmation.
2. Real migration shipped + verified working.
3. Migration registry + future stubs listed.
4. Coverage + test count deltas.
5. Anything that surfaced about idempotency / reversibility (escalate).
