# v0.10.30 — Villager Architect Findings Index

**Author:** Villager Architect
**Date:** 2026-05-01
**Branch:** `claude/villager-multi-agent-setup-sUBO6`
**Plan that led to this:** `team/villager/architect/v0.10.30__plan__deep-analysis.md`
**Consolidated narrative:** `99__consolidated-report.md`

---

## How to read this

Each `NN__topic.md` file is a self-contained finding. Files are independent —
read in any order. The consolidated report (`99__`) ties them together for
readers who want one narrative.

Verdicts use three labels:
- `BOUNDARY OK` — change respects Explorer-defined boundaries.
- `BOUNDARY DRIFT` — boundaries violated; refactor candidate (Phase 3).
- `SEND-BACK-TO-EXPLORER` — needs architectural redesign, not hardening.

**No SEND-BACK findings in this sprint.**

---

## Findings table

| File | Topic | Verdict | Severity | Owner(s) |
|---|---|---|---|---|
| `01` | HMAC-IV crypto boundary — change is correct, but ships with zero tests for the headline determinism claim | BOUNDARY OK + test debt | HIGH | Architect + AppSec, hand-off to QA |
| `02` | New CLI commands — `probe`, `delete-on-remote`, `rekey`, `write` — all thin dispatch, boundaries respected | BOUNDARY OK | LOW | Architect, hand-off to Dev for cosmetic |
| `03` | Vault format + CLI contract — `bare/*` unchanged, but two new local files (`push_state.json`, `clone_mode.json`) bypass schema; debrief 01 mis-states `clone_mode.json` shape | BOUNDARY OK + docs drift | LOW (with cross-ref to 05) | Architect + Sherpa |
| `04` | Duplication and pipeline shape — two BFS implementations, two tree-build pipelines, three blob-encrypt sites; HMAC-IV change had to be made in two places | BOUNDARY DRIFT (refactor) | HIGH | Dev (Phase 3) |
| `05` | Type_Safe hygiene — `Schema__Local_Config` no longer matches its file; `push_state.json` and `clone_mode.json` have no schema at all | BOUNDARY DRIFT (rule violation) | HIGH | Dev (Phase 3) |
| `06` | Resumable push state — design correct, but `delete-on-remote` followed by `push` leaves the server with commits pointing at deleted blobs | BOUNDARY OK + edge-case bug | MEDIUM | Dev + QA |
| `07` | Sparse mode and progress-bar contract — sparse stored in `local_config.json` (not `clone_mode.json` as debrief claims); no promotion path from sparse → full | BOUNDARY OK + design ambiguity | MEDIUM | Sherpa decision, then Dev |
| `08` | Tests review — HMAC-IV has zero coverage; probe-share path untested; rekey-empty-vault test passes for wrong reason; read-only guard tested only at CLI | BOUNDARY DRIFT (test debt) | HIGH | QA + Dev |
| `99` | Consolidated narrative report | — | — | — |

---

## Top 3 risks (one-line)

1. **HMAC-IV change is unprotected by tests** — the headline crypto claim
   has no assertions. (Finding 01, 08.)
2. **`Vault__Sync.py` is 2,986 lines and has visible duplication** — two
   BFS implementations, two tree-build pipelines. (Finding 04.)
3. **`local_config.json` schema lies about the file** — four undeclared
   fields in production, schema declares only one. (Finding 05.)

## Top 3 quick wins (one-line)

1. Add 5 unit tests for HMAC-IV determinism (finding 01, section 4).
2. Add `_clear_push_state` to `delete_on_remote` flow — single-line fix
   (finding 06.2d).
3. Extend `Schema__Local_Config` with `mode`, `edit_token`, `sparse` —
   matches what's already on disk (finding 05.1).

## Hand-off matrix

| Role | Items |
|---|---|
| **AppSec** | Cryptanalytic threat model for HMAC-IV (01); read-only guard duplication (02); orphan push-state on `delete_on_remote` (06) |
| **Dev** | All BOUNDARY DRIFT items (04, 05); domain-side read-only guard (02); cosmetic `cmd_write` consistency (02); orphan-checkpoint cleanup (06) |
| **QA** | Missing HMAC-IV tests (01, 08); missing probe-share test (08); orphan-checkpoint test scenarios (06); sparse-pull working-copy test (07); round-trip tests for new schemas (05) |
| **Sherpa** | Sparse promotion model (07); `Vault__Sync.py` split for Phase 4 (04); `Schema__Local_Config` evolution call (03, 05); rekey-on-read-only clones policy (02) |
| **Designer** | `✓` / `·` glyph compatibility (07) |

---

## Final commit / push status

This document is the last in the v0.10.30 directory; commit history on
this branch shows incremental commits as findings were drafted (cadence
of every 2–3 files per push). Branch is `claude/villager-multi-agent-setup-sUBO6`.
