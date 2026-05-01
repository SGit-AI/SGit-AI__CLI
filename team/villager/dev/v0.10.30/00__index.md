# Villager Dev — v0.10.30 Findings Index

**Author:** Villager Dev
**Date:** 2026-05-01
**Sprint range:** commits `bc10167…4d53f79` (Apr 20 – May 1, 2026)
**Branch:** `claude/villager-multi-agent-setup-sUBO6`

For the narrative read, see `99__consolidated-report.md`.

---

## Findings (one file per focus area)

| # | File | Severity | Topic — one-line summary |
|---|------|----------|--------------------------|
| 01 | [`01__type-safe-compliance.md`](01__type-safe-compliance.md) | major | 9 new `Vault__Sync` methods return raw `dict` instead of `Schema__*`; no new `Safe_*`/`Schema__*` classes added this sprint |
| 02 | [`02__mocks-and-patches.md`](02__mocks-and-patches.md) | major | 553 mock-pattern lines (carryover); 0 new `unittest.mock` imports this sprint; 4 new homemade `FakeArgs` stubs in `test_CLI__Vault__Write.py` |
| 03 | [`03__cli-init-purity-and-class-pattern.md`](03__cli-init-purity-and-class-pattern.md) | info | PASS — `cli/__init__.py` is 7 lines; all 11 new commands are `cmd_*` methods on `CLI__Vault` |
| 04 | [`04__tests-tree-init-files.md`](04__tests-tree-init-files.md) | info | PASS — zero `__init__.py` files under `tests/` |
| 05 | [`05__duplication-across-new-commands.md`](05__duplication-across-new-commands.md) | minor | Token-derivation duplicated between probe and clone; `clone_mode.json` write duplicated; 7+ copies of branch-index guard |
| 06 | [`06__file-size-and-class-seams.md`](06__file-size-and-class-seams.md) | major | `Vault__Sync.py` at 2986 LOC and `CLI__Vault.py` at 1381 LOC — Architect-owned class-split flagged; 8+4 candidate sub-classes mapped |
| 07 | [`07__test-quality-new-features.md`](07__test-quality-new-features.md) | major | Per-feature test gaps: resumable push checkpoint untested; share-token probe branch untested; 5 test bugs (B1–B5) flagged |
| 08 | [`08__error-handling-consistency.md`](08__error-handling-consistency.md) | minor | `probe_token` swallows real errors as "not found"; push-checkpoint silently restarts on corrupted JSON; read-only guard fails **open** on malformed `clone_mode.json` |
| 09 | [`09__crypto-determinism-test-coverage.md`](09__crypto-determinism-test-coverage.md) | **major** (potential blocker) | `encrypt_deterministic` and `encrypt_metadata_deterministic` have ZERO direct tests; no browser interop vector; rule violation of "test vectors mandatory" |
| 10 | [`10__state-files-schema.md`](10__state-files-schema.md) | minor | New `clone_mode.json` and `push_state.json` are persisted as raw `dict` — no `Schema__*` class, no round-trip test |

## Severity rollup

| Severity | Count | Findings |
|----------|------:|----------|
| blocker  | 0     | (none — finding 09 escalates to major-pending-AppSec) |
| major    | 5     | 01, 02, 06, 07, 09 |
| minor    | 3     | 05, 08, 10 |
| info     | 2     | 03, 04 |

## Baseline-delta vs v0.5.11

| Metric | v0.5.11 final | v0.10.30 (this review) | Delta |
|--------|--------------:|-----------------------:|-------|
| Type_Safe compliance | 94% | unchanged for class fields; eroded for new method shapes (9 methods) | drift |
| Mock violations (uniques) | 18 | not directly comparable; raw-line count is 553 (incl. monkeypatch); 4 new homemade stubs | regression in spirit, flat in `unittest.mock` imports |
| Largest source file (LOC) | ~2400 | 2986 (`Vault__Sync.py`) | **+25%** |
| New schemas added | n/a | **0** new `Schema__*` despite 2 new persisted JSON shapes | regression |
| Crypto test-vector compliance | (existing primitives covered) | new `encrypt_deterministic` has no test vector | regression |

## Escalations (cross-team handoff)

- **Architect:** findings 01 (return shapes), 05 (extraction seams),
  06 (class-split), 10 (schema names)
- **AppSec:** findings 09 (crypto determinism), 8.6 (fail-open
  read-only guard), 02 sub-2.2 (`MagicMock` security-test smell)
- **QA:** finding 07 (per-feature coverage gaps)

## Read order

For the narrative: open `99__consolidated-report.md`. For the
critical issues: 09 → 07 → 06 → 02 in that order.
