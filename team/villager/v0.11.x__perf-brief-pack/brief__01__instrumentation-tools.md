# Brief B01 — Instrumentation + Visualisation Tools (Phase 0)

**Owner role:** **Villager Dev** (`team/villager/dev/dev__ROLE.md`)
**Status:** Ready to execute. **First brief in the pack** — runs before any main-command change.
**Prerequisites:** None.
**Estimated effort:** ~6–10 hours (5 small CLI tools)
**Touches:** new code under `sgit_ai/cli/dev/` (new sub-package), tests under `tests/unit/cli/dev/`. **Read-only on existing main-command paths.**

---

## Why this brief exists

Per Dinis's principle: "before we make any code changes to the main commands, let's really write a lot of code and utilities that are focused on visualisation, understanding, step-by-step executions."

The clone case study (~202s, 91% in tree walking, 2,375 trees serving 165 files) needs **measurement-grade tooling** before we design fixes. Five small CLI tools serve that need.

---

## Required reading

1. This brief.
2. `team/villager/dev/dev__ROLE.md`.
3. `team/villager/v0.11.x__perf-brief-pack/01__sprint-overview.md`.
4. `team/villager/v0.11.x__perf-brief-pack/design__02__cli-command-surface.md` (where these tools live: `sgit dev <…>`).
5. `sgit_ai/sync/Vault__Sync.py` `_clone_with_keys` (line 1276–1410) — the path to instrument.
6. `sgit_ai/api/Vault__API.py` `batch_read` and friends — the network layer.
7. `CLAUDE.md` — Type_Safe + no-mocks rules.

---

## Scope

Implement five tools, each as a Type_Safe class under `sgit_ai/cli/dev/`:

### 1. `sgit dev profile clone <vault-key> <directory>`

Runs the existing clone path with detailed instrumentation. Output:

- Per-phase wall-clock (already in trace; expand to per-wave).
- Per-wave (BFS): wave number, wave size, HTTP wall-clock, decrypt wall-clock, JSON-parse wall-clock.
- Per-tree top-N slowest: tree-id, decrypt time, parse time, entry count.
- HTTP call count + bytes downloaded.
- Tree-id frequency across history (for hypothesis H3 verification — see strategy doc).

Output formats:
- Default: text summary
- `--json` flag: machine-readable JSON dumped to a path of choice

### 2. `sgit dev tree-graph <vault-key>`

Visualise the tree DAG without modifying the working copy. Outputs:

- Textual representation of the tree DAG (commit → root tree → subtrees).
- Per-commit: total trees rooted, unique trees added, dedup ratio.
- Per-depth-level histogram of tree count.
- "If we cloned only HEAD" counterfactual: tree count.
- Optional Graphviz `.dot` output.

### 3. `sgit dev server-objects <vault-key>`

Inventory of remote objects without downloading bodies (use existing API list endpoints; if missing, use a `HEAD`-style probe):

- Total object count by type (commit / tree / blob / index / ref / key).
- Reachable from HEAD vs only from history.
- Largest N objects (post-decrypt size — requires download for sample).
- Hot tree-ids (referenced from many commits).

### 4. `sgit dev step-clone <vault-key> <directory>`

A clone that pauses between phases. After each phase prints what just happened, what files were created, what's next; waits for `<Enter>` to proceed (`--no-pause` for non-interactive).

This is a precursor to the workflow framework (B05); when B05/B06 land, this becomes a thin wrapper over the workflow trace mode.

### 5. `sgit dev replay <trace.json> [--diff <other-trace.json>]`

Records a clone trace to JSON; replays it offline (no network, just timing math). Supports diff mode to compare two traces for before/after analysis.

Pairs with the `--json` output of `dev profile clone`.

---

## Hard constraints

- All five tools are **read-only on the network** (well, profile/step actually clone — but they don't write to the server).
- All five are **read-only on existing main-command source paths**. Do not modify `_clone_with_keys` to add instrumentation; instead, monkey-... no wait, no patching either. Write a sibling instrumented clone path that imports and wraps the existing one with hook callbacks. The existing clone path already accepts `on_progress` callbacks — extend that mechanism to a richer hook interface if needed (a single small additive change to `Vault__Sync` is acceptable, but it must not change main-command behaviour).
- New sub-package `sgit_ai/cli/dev/` for the tool classes.
- Tests under `tests/unit/cli/dev/`. No mocks; real in-memory transfer server for fixture data.
- Type_Safe everywhere. New schemas for the JSON output formats.
- Honour Phase B test infra: tests must pass under `pytest tests/unit/ -n auto`.

---

## Acceptance criteria

- [ ] Five CLI tools registered as `sgit dev <…>` subcommands (or stub `sgit dev <…>` namespace if the namespace work in B02 hasn't merged yet — coordinate).
- [ ] Each tool has a Type_Safe schema for its JSON output.
- [ ] At least 3 tests per tool (happy-path, edge-case, error-path) using real fixtures.
- [ ] Coverage on the new code ≥ 80%.
- [ ] No modification to existing main-command code paths beyond an optional richer `on_progress` hook signature.
- [ ] Suite ≥ existing test count + N passing; coverage delta non-negative.
- [ ] Closeout note appended to `team/villager/v0.11.x__perf-brief-pack/01__sprint-overview.md` with file paths to the 5 tool classes.

---

## Out of scope

- Implementing fixes (Phases 3+). Just instrumentation.
- The full workflow framework (brief B05).
- The CLI namespace registration (brief B02 — coordinate; if B02 hasn't merged, register a minimal `dev` parser locally and let B02 fold it in).
- Server-side instrumentation. Client-side measurements only.

---

## Deliverables

- Source files under `sgit_ai/cli/dev/`.
- Test files under `tests/unit/cli/dev/`.
- Closeout note in sprint overview.

Commit cadence: one commit per tool, pushed periodically. Avoid one mega-commit.

Commit message template:
```
feat(dev): sgit dev <tool-name>

Phase-0 instrumentation tool. Adds <tool-name> for <purpose>.
Output format: <text|json>. Closes B01 acceptance criterion N.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 250-word summary:
1. Tool names + their CLI invocation.
2. JSON schema names per tool.
3. Test count + coverage delta.
4. Any modification made to main-command code (justify).
5. First-look numbers from running `dev profile clone` against the case-study vault — confirms or refutes hypotheses H1–H4 from the strategy doc.
