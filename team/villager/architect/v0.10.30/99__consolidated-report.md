# v0.10.30 Architect Deep-Analysis — Consolidated Report

**Author:** Villager Architect
**Date:** 2026-05-01
**Branch:** `claude/villager-multi-agent-setup-sUBO6`
**Scope:** Sprint v0.10.30 (Apr 20 – May 1, 2026), 7 feature clusters
**Source documents:** debriefs `00`–`07`, `Vault__Sync.py` (2,986 lines),
`Vault__Sub_Tree.py`, `Vault__Crypto.py`, `Vault__Storage.py`, `CLI__Vault.py`,
plus all `tests/unit/{sync,crypto,cli}/` files touched in the sprint.

---

## 1. Executive verdict

The sprint shipped **seven feature clusters** that respect the architectural
boundaries Explorer set. **No SEND-BACK-TO-EXPLORER findings.** The Sonnet
team understood where domain logic belongs (`Vault__Sync` and friends) and
kept CLI handlers thin. Crypto changes stayed inside `Vault__Crypto` and
`Vault__Sub_Tree`. The on-disk vault format proper (`bare/*`) is unchanged.

That's the good news. The structural debt accumulated in three places:

1. **`Vault__Sync.py` is now 2,986 lines** — a single class is hosting the
   entire sync surface, and 22 commits in two weeks have left visible
   duplication scars (two BFS implementations, two tree-build pipelines,
   three "encrypt-blob-or-reuse" sites). Each is a Phase-3 refactor target.

2. **Three on-disk JSON files now bypass Type_Safe** — `push_state.json` and
   `clone_mode.json` have no schema at all, and `local_config.json` accumulates
   four undeclared fields (`mode`, `edit_token`, `sparse`, plus the schema's
   one declared field). The schema no longer tells the truth about the file.

3. **The headline architectural claim of the sprint — HMAC-IV deduplication
   — has zero tests.** The crypto change shipped in commit `4d53f79` with no
   test additions; the follow-up commit `c249f91` only fixes an existing
   regression. The debrief's "3 determinism assertions" do not exist.

---

## 2. Findings index by severity

| # | Topic | Verdict | Severity |
|---|---|---|---|
| 01 | HMAC-IV crypto boundary | BOUNDARY OK + missing tests | HIGH (test debt) |
| 02 | New commands' CLI boundary | BOUNDARY OK | LOW |
| 03 | Vault format / CLI contract | BOUNDARY OK + debrief drift | LOW |
| 04 | Duplication and pipeline shape | BOUNDARY DRIFT (refactor candidate) | HIGH (code mass) |
| 05 | Type_Safe hygiene | BOUNDARY DRIFT (rule violation) | HIGH (3 schemas missing) |
| 06 | Resumable push state | BOUNDARY OK + edge-case bug (delete-on-remote orphan) | MEDIUM |
| 07 | Sparse mode and progress contract | BOUNDARY OK + design ambiguity (sparse promotion) | MEDIUM |
| 08 | Tests review | BOUNDARY DRIFT (test debt) | HIGH (headline claim untested) |

---

## 3. Top 3 issues — narrative

### 3.1 The HMAC-IV change has no tests for its actual claim

The deterministic-IV change is the biggest crypto behaviour change in months.
It directly touches the security model — IND-CPA is preserved only
because the IV depends on the key, not just the plaintext. **None of this is
asserted in unit tests.**

The change is correct as far as I can tell from inspection: every relevant
caller of `encrypt_metadata` was migrated to `encrypt_metadata_deterministic`,
the determinism property is honest, and backward-compat (old random-IV
objects still decrypt) is preserved by the format-agnostic `decrypt()` path.
But "as far as I can tell from inspection" is a poor substitute for
assertions in CI.

This is **the most important follow-up of the sprint**. Five concrete
test cases are listed in finding 01.

### 3.2 `Vault__Sync.py` has structural duplication that bit the sprint already

Two BFS implementations (clone vs pull) with diverging optimisations
(`stop_at` exists in pull but not clone). Two `Vault__Sub_Tree.build*`
methods with 140 lines of nearly-identical code — **the HMAC-IV change had
to be applied to both, in lockstep**, which is exactly the kind of
distributed change that misses one site under pressure.

The proposed Phase-3 refactor — extract `Vault__Graph_Walk`, unify
`build*`, and pull blob bucketing into `Vault__Object_Store` — would remove
~300 lines and make every future BFS bug fix a one-line change. Finding 04
has the full hit-list.

### 3.3 Three on-disk JSON files have no schema

`Schema__Local_Config` declares `my_branch_id` and nothing else. The file
on disk has at least four fields. `push_state.json` and `clone_mode.json`
have no schema at all. Type_Safe rule 1 ("Zero raw primitives in Type_Safe
classes") is violated by the implementation, even though no Type_Safe
*class* declares a raw primitive.

This is a slow-burn issue: as long as everything keeps working, no one
notices. But the moment Sonnet (or anyone) needs to evolve any of these
schemas — adding a new field, supporting v1 → v2 migration, validating
on read — the absence of a schema turns into a `if 'foo' in d:` audit
across every read site. Finding 05 has the proposed schemas.

---

## 4. Send-back-to-Explorer list

**None.** All findings are hardening / Phase-3 refactor candidates that the
Villager team can address without re-engaging Explorer.

The closest candidates were:
- HMAC-IV cryptanalytic risk (finding 01) — but this is AppSec's call, and
  if AppSec is satisfied, the change stays.
- Sparse-mode promotion semantics (finding 07) — but Sherpa can decide this
  without Explorer.
- "Should `rekey` be allowed on read-only clones?" (finding 02) — small
  enough that Architect+Dev can resolve without a redesign.

If AppSec returns a finding that HMAC-IV has unacceptable leakage, that
becomes a SEND-BACK. I'm not anticipating that.

---

## 5. Joint follow-ups

| Joint role | Topic | Source finding |
|---|---|---|
| Architect + AppSec | HMAC-IV cryptanalytic risk envelope | 01 |
| Architect + AppSec | Read-only guard duplication: CLI vs domain | 02 |
| Architect + Dev | Domain-layer read-only guard for `write_file` | 02, 08 |
| Architect + Sherpa | Sparse promotion semantics | 07 |
| Architect + Sherpa | `Vault__Sync.py` split (Phase 4) | 04 |
| Architect + Dev | Schema additions: `Schema__Push_State`, `Schema__Clone_Mode`, `Schema__Local_Config` extension | 05 |
| Architect + QA | "Tests must back debrief claims" rule for next sprint | 08 |

---

## 6. What I deliberately didn't do

Per Villager rules and the brief:

- **No source/test edits.** Read-only review.
- **No design proposals beyond "extract X" / "add Schema Y".** Where the
  shape of the right-thing is non-obvious (e.g. sparse promotion model), I
  flagged a Sherpa decision rather than picked.
- **No threat-model work on HMAC-IV.** AppSec's lane.
- **No coverage measurement.** Spot-checks of test files, not a coverage
  run.

---

## 7. Documents in this directory

- `00__index.md` — table of contents
- `01__hmac-iv-crypto-boundary.md`
- `02__new-commands-cli-boundary.md`
- `03__vault-format-and-cli-contract.md`
- `04__duplication-and-pipeline-shape.md`
- `05__type-safe-hygiene-on-additions.md`
- `06__resumable-push-state.md`
- `07__sparse-mode-and-progress-contract.md`
- `08__tests-review.md`
- `99__consolidated-report.md` (this file)

Total: 9 finding documents + index. All under the 200-line guideline.
