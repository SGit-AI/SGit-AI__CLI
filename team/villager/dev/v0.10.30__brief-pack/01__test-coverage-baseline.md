# Brief 01 — Test Coverage Baseline (v0.10.30)

**Phase:** A — Measure
**Owner role:** **Villager QA** (`team/villager/qa/qa__ROLE.md`)
**Status:** Ready to execute
**Prerequisites:** None
**Estimated effort:** ~45 min
**Read-only:** YES — this brief MUST NOT modify source or tests.

---

## Why this brief exists

The v0.10.30 deep-analysis review (cross-team summary §5.3) flagged three
test-coverage gaps already known by inspection:
1. `encrypt_deterministic` / `encrypt_metadata_deterministic` — zero direct tests.
2. Resumable-push checkpoint triplet — zero direct tests.
3. `probe_token` share-token branch — zero coverage.

Inspection numbers are not a baseline. Before the team starts adding tests
or refactoring, capture **exact** coverage numbers so every change after
this point has a measurable delta.

The previous QA baseline (`team/villager/qa/v0.5.11__coverage-baseline.md`,
March 2026) reported 83% / 1,981 of 2,381 lines. We need a fresh number
for the v0.10.30 codebase, which has shipped ~600 net LOC of new code in
two weeks.

---

## Scope

You will produce a single small markdown document:

`team/villager/qa/v0.10.30__coverage-baseline.md`

Mirror the structure of `v0.5.11__coverage-baseline.md` but for the
current state of `claude/villager-multi-agent-setup-sUBO6` (synced with
`origin/dev`).

**You may run pytest with coverage. Running tests is allowed and
expected.** What you may NOT do:

- Modify any source file under `sgit_ai/`.
- Modify any test file under `tests/`.
- Add or remove dependencies.
- Change `pytest.ini`, `pyproject.toml`, `setup.cfg`, `.coveragerc`, etc.
- Commit anything other than the new baseline doc.

---

## Required reading

1. This brief (in full).
2. `team/villager/qa/qa__ROLE.md` — your role.
3. `team/villager/qa/v0.5.11__coverage-baseline.md` — match its format.
4. `CLAUDE.md` at repo root — note: integration tests need Python 3.12 venv.
5. `team/villager/v0.10.30__next-phase-plan.md` §2(a) — context for why
   this measurement matters.

Do not read the full cross-team-summary or the 32 deep-analysis findings;
they are background for the deferred queue, not for this baseline.

---

## What to measure

### A. Headline numbers

```bash
pytest tests/unit/ --cov=sgit_ai --cov-report=term-missing --cov-report=json:coverage.json
```

Capture:
- Test counts: passed / failed / skipped / errors / xfailed.
- Total runtime (wall clock) — record both python version and pytest version.
- Overall coverage % (lines covered / lines total).
- Branch coverage if `--cov-branch` is feasible without changing config (try it; if it errors, note that and fall back to line coverage).

### B. Per-module coverage

Group source files by sub-package. For each, record:

| Sub-package | Files | Lines | Covered | % |
|---|---:|---:|---:|---:|
| `sgit_ai/api/` | … | … | … | … |
| `sgit_ai/cli/` | … | … | … | … |
| `sgit_ai/crypto/` | … | … | … | … |
| `sgit_ai/objects/` | … | … | … | … |
| `sgit_ai/pki/` | … | … | … | … |
| `sgit_ai/safe_types/` | … | … | … | … |
| `sgit_ai/schemas/` | … | … | … | … |
| `sgit_ai/secrets/` | … | … | … | … |
| `sgit_ai/sync/` | … | … | … | … |
| `sgit_ai/transfer/` | … | … | … | … |

### C. Files at 100% coverage

List them, but only the count is mandatory; sample names if the list is
long.

### D. Files below 50% coverage

This is the priority audit. For each:
- File path
- Coverage %
- Line count
- One-sentence note: which paths/methods are uncovered (use `--cov-report=term-missing` output for line ranges).

### E. Specifically-flagged-by-deep-analysis paths

Verify the three known gaps against measured numbers:
1. `sgit_ai/crypto/Vault__Crypto.py` — coverage of `encrypt_deterministic` and `encrypt_metadata_deterministic` lines.
2. `sgit_ai/sync/Vault__Sync.py` — coverage of `_load_push_state`, `_save_push_state`, `_clear_push_state`, and `probe_token`'s share-token branch (around lines 1820–1830).
3. Any `bare/data/{blob_id}` ciphertext-vs-plaintext assertion: search test code for occurrences of `bare/data` and report whether `write_file`'s output is asserted as ciphertext anywhere.

For each, report the actual coverage status. If a "known gap" is in fact
covered, that's a finding to flag.

### F. Delta vs v0.5.11

A small table comparing v0.5.11 → v0.10.30:

| Metric | v0.5.11 | v0.10.30 | Delta |
|---|---:|---:|---:|
| Tests passed | 430 | … | … |
| Tests skipped | 28 | … | … |
| Total lines | 2,381 | … | … |
| Lines covered | 1,981 | … | … |
| Coverage % | 83% | … | … |
| Suite runtime | ~53s | … | … |

(Note: v0.5.11 used `sg_send_cli` package name. v0.10.30 uses `sgit_ai`.
Match by current package only; comparison is approximate.)

---

## Acceptance criteria

Before you mark this brief complete, verify:

- [ ] Baseline doc exists at `team/villager/qa/v0.10.30__coverage-baseline.md`
      and is ≤ 250 lines.
- [ ] All six sections (A–F) above are populated with real numbers from
      a fresh pytest run, not estimates.
- [ ] The pytest command, Python version, and pytest version used are
      recorded at the top of the doc (so the run is reproducible).
- [ ] Working tree is clean except for the new baseline doc.
- [ ] No source or test file was modified (verify `git diff` is empty
      against `sgit_ai/` and `tests/`).
- [ ] Doc is committed and pushed.

---

## Deliverable

One file: `team/villager/qa/v0.10.30__coverage-baseline.md`.

Commit message:
```
docs(villager-qa): capture v0.10.30 coverage baseline

Headline: NNN passed, NN skipped, X% line coverage, NNs runtime.
Below v0.5.11 baseline by N pp / above by N pp on the new sgit_ai package.

Three known gaps from cross-team review confirmed:
- encrypt_deterministic / encrypt_metadata_deterministic
- _load/save/clear_push_state
- probe_token share-token branch

Read-only — no source or test changes.

https://claude.ai/code/session_<id>
```

Then `git push origin claude/villager-multi-agent-setup-sUBO6`.

---

## Out of scope

- Writing any test (that's brief 03–04 territory).
- Refactoring any test (that's brief 04 + Phase 3).
- Recommending which gaps to fill first (defer to brief 03's design phase
  and brief 06's acceptance criteria).
- Coverage thresholds (set in brief 06).
- Integration tests (Python 3.12 venv) — note their existence but do not
  run them in this brief; unit tests only for the baseline.

---

## When you finish

Return a summary stating:
1. Headline coverage % and runtime.
2. Top 5 worst-covered files (path + %).
3. Confirmation status of the three known gaps from §E.
4. Anything in the v0.5.11 → v0.10.30 delta that surprised you.
5. Anything you couldn't measure within the time budget.
