# Brief B02 — Migration Command

**Owner:** **Villager Dev**
**Status:** Ready. **Highest-leverage perf brief** for old vaults (was B10 in v0.12.x).
**Estimated effort:** ~2 days
**Touches:** new `sgit_ai/migrations/` package, new `sgit migrate` (or under `sgit vault migrate <…>`) command, schemas, tests.

---

## Why this brief exists

The B07 case-study diagnosis confirmed the **single biggest perf win for old vaults** (created before May 1 / pre-HMAC-IV) is **migrating their tree objects to deterministic IVs**. Before migration the case-study vault has 2,375 unique tree-IDs (no dedup); after migration ~300 unique trees. **Expected speedup: 7–8× on full clones of pre-migration vaults.**

This is **client-side only**. No backend changes. **It's the lever that lets us defer B08 server packs.**

The previous v0.12.x B10 brief had migration framework scaffolding only. This brief implements a real, useful first migration.

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` — the H3 confirmation.
3. `team/villager/v0.12.x__perf-brief-pack/brief__10__migration-command.md` — the original (lighter) migration brief.
4. The HMAC-IV change in `sgit_ai/crypto/Vault__Crypto.py` (post-May-1) — understand what "deterministic IV" means for tree objects.
5. `sgit_ai/storage/Vault__Sub_Tree.py` and `Vault__Object_Store.py` — the storage layer the migration operates on.

---

## Scope

### Step 1 — Migration framework

Create `sgit_ai/migrations/`:

- `Migration.py` — Type_Safe base class with `name`, `from_version`, `to_version`, `is_applied(vault) -> bool`, `apply(vault) -> dict` (returns stats).
- `Schema__Migration_Record.py` — what's persisted per applied migration.
- `Schema__Migrations_Applied.py` — list of records, persisted to `.sg_vault/local/migrations.json`.
- `Migration__Registry.py` — discovers all `Migration` subclasses, exposes them in order.
- A small `Migration__Runner` that handles plan / apply / status flows (idempotent).

### Step 2 — First real migration: tree-IV re-encryption

`Migration__Tree_IV_Determinism`:
1. **Pre-condition check** — vault has objects encrypted with random IVs (detect by sampling a tree object's IV and comparing to the HMAC-derived expected IV).
2. **Apply**:
   - For every tree object in the vault, decrypt → re-encrypt with the deterministic HMAC-derived IV → store under the new (now-deterministic) object-id.
   - Update commit objects to point at the new tree object-ids.
   - Remove the old random-IV tree objects.
   - For paranoia: keep a backup at `.sg_vault/local/pre-migration-trees.json` (just the old object-ids, not the data) so the migration is auditable.
3. **Mark applied** in `migrations.json`.
4. **Return stats**: trees re-encrypted, commits rewritten, dedup ratio achieved.

### Step 3 — CLI surface

Top-level `sgit migrate` (or `sgit vault migrate <…>` per Dinis preference):
- `sgit migrate plan` — what migrations would apply (read-only).
- `sgit migrate apply` — execute pending migrations.
- `sgit migrate status` — what's applied, when, with stats.

### Step 4 — Tests

- `Migration` round-trip tests (Type_Safe schemas).
- `Migration__Tree_IV_Determinism` tests using `Vault__Test_Env.setup_single_vault()` with **synthetically-generated random-IV trees** to simulate an old vault.
- End-to-end: vault → `migrate plan` → `migrate apply` → verify dedup ratio improves; clone time after migration is measurably faster.
- Idempotency: `migrate apply` twice = no-op the second time.
- Failure mid-migration: assert the vault is left in a usable state (either old or new, not half-migrated).

---

## Hard rules

- **Type_Safe everywhere.**
- **No mocks** — use `Vault__Test_Env` + in-memory transfer server.
- **Idempotent** — re-running a completed migration is a no-op.
- **Reversible where feasible** — keep enough info to detect "already migrated" (the audit JSON above).
- **Coverage must not regress.**
- **Behaviour preservation post-migration** — full clone of a migrated vault produces a working tree byte-identical to a fresh full clone of the same logical content.

---

## Acceptance criteria

- [ ] `sgit_ai/migrations/` package exists with `Migration`, `Migration__Runner`, `Migration__Registry`.
- [ ] `Migration__Tree_IV_Determinism` implemented + tested end-to-end.
- [ ] `sgit migrate plan / apply / status` CLI works.
- [ ] Tests demonstrate dedup improvement on a synthetic random-IV vault: pre-migration N unique trees → post-migration ~ N/dedup_ratio.
- [ ] Idempotency test passes.
- [ ] Mid-migration failure test passes.
- [ ] Suite ≥ 3,068 + ~10 new tests passing.
- [ ] Coverage delta non-negative.

---

## Closeout — re-measurement gate

After this brief lands, **re-run B07's diagnosis** on a migrated case-study vault (or representative). The deferred-B08 decision depends on it:

- If clone time post-migration is < 30s on the case-study profile: **B08 stays archived** for v0.14+.
- If still > 30s consistently: **pull B08 + B08b out of archive** and re-prioritise.

Append the re-measurement to `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` as §"Post-migration re-measurement (2026-05-XX)".

---

## When done

Return a ≤ 250-word summary:
1. Migration framework implemented (file paths).
2. First migration shipped + verified end-to-end.
3. Dedup improvement achieved on a synthetic test (numbers).
4. Test count + coverage delta.
5. Re-measurement result on the case-study vault — recommendation on whether B08 stays archived.
