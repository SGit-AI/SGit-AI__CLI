# Design — Coverage Roadmap (D5)

**Status:** Captured. Drives briefs B05 + B06.

## Current state

| Metric | Value | Source |
|---|---:|---|
| Overall coverage | 88% | B22 plan §"Prerequisites status" |
| Uncovered lines (approx) | ~1,200 | derived from 88% of ~10k stmts |
| Largest single file gap | `Vault__Sync.py` 81% / 374 missed lines | B22 plan §1 |

## Target

**≥ 92% by end of B22.** **≥ 95% by mid-v0.11.x.** Not 100%; the
trailing 5% is typically defensive code (catch-all `except Exception:`,
unreachable branches in CLI argparse, Type_Safe defaults) where the
ROI is low.

## The four paths to high-90s

### Path A — B22 sub-class direct tests (already in flight)

Per the B22 addendum: each `Vault__Sync__<X>` extraction lands ≥ 5
direct tests. ~10 sub-classes × 5 tests = **50+ new direct tests**.
Should close ~150–200 of the 374 missed `Vault__Sync.py` lines.

**Owner:** B22 executor session (already running). No new brief needed.
**Expected delta:** +2 to +3 percentage points.

### Path B — Long-tail error paths

Many `sgit_ai/sync/` and `sgit_ai/api/` methods have `except Exception:`
catch-alls that no test exercises. Examples:

- `Vault__Sync.py` `_load_push_state` — corrupt JSON path
- `Vault__API.batch_read` — HTTP 502/503 retry path (partial coverage)
- `Vault__API.presigned_read_url` — error mapping
- `API__Transfer` — `HTTPError` branches
- `Vault__Inspector.inspect_*` — corrupt-on-disk paths

**Owner:** Brief **B05** (Villager Dev + QA).
**Approach:** systematic enumeration via `coverage report --show-missing`
filtered to `except` blocks. Target test list per file.
**Expected delta:** +2 percentage points.

### Path C — Direct CLI handler tests

CLI handler methods (`CLI__Vault.cmd_*`, `CLI__Main.cmd_*`) get
coverage indirectly through CLI invocation tests. Direct handler-level
tests:
- Faster to write (no argparse trip, no full CLI invocation).
- Catch handler bugs unrelated to argument parsing.
- Cover error paths (the handler raises X when state Y).

**Owner:** Brief **B06** (Villager Dev + QA).
**Approach:** for each `cmd_*` method, add at least one direct
"happy-path" + one "error-path" test.
**Expected delta:** +1 to +2 percentage points.

### Path D — Plugins coverage (post-v0.11.x B14)

When v0.11.x B14 lands, every read-only namespace becomes a plugin
under `sgit_ai/plugins/<name>/` with its own `tests/` subdir. Per-plugin
coverage targets become natural:
- `history` plugin: ≥ 95%
- `inspect` plugin: ≥ 95%
- `file` plugin: ≥ 95%
- `check` plugin: ≥ 90%
- `dev` plugin: ≥ 80% (lower target — many dev tools are exploratory)

**Owner:** v0.11.x B14 + ongoing.
**Expected delta:** maintains coverage as code moves; doesn't add
percentage points but prevents regression during the big move.

---

## Sequencing

```
Now             ← 88% (per B22 plan)
   │
B22 sub-class direct tests (Path A)
   │            ← projected 90–91%
B05 long-tail error paths (Path B)
   │            ← projected 92–93%
B06 direct CLI handler tests (Path C)
   │            ← projected 94–95%
v0.11.x B14 plugin coverage (Path D)
                ← maintains 94–95% through layered restructure
```

## Out-of-scope (deliberately)

- **Coverage of code we plan to delete.** v0.11.x B13 dissolves
  `Vault__Sync.py`; covering its dying corners is wasted work.
  Path A sub-class tests transfer to the new structure (per the B22
  addendum). Anything else in `Vault__Sync.py` that doesn't survive
  B13 is not worth covering.
- **Coverage of code we plan to refactor heavily.** Covering
  `_clone_with_keys` line-by-line is moot when v0.11.x B06 reformulates
  it as a `Workflow__Clone`. Existing CLI-level tests are sufficient
  until then.
- **Coverage of `cli/CLI__Main.py` argparse glue.** Argparse trees are
  generated; covering every branch is low-ROI. Skip below 70% on this
  file specifically; it's documented as acceptable.

## Acceptance for this design

- Four paths named with owner + expected delta.
- Sequencing agreed.
- Out-of-scope items explicit.
- B05 + B06 each have a clear scope.
