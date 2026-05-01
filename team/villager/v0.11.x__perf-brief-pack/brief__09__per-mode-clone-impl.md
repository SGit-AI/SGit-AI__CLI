# Brief B09 — Per-Mode Clone Implementations

**Owner role:** **Villager Dev** (Explorer-blessed for any new step types)
**Status:** BLOCKED until briefs B03 + B06 + B08 land.
**Prerequisites:** B03 (clone-family stubs), B06 (workflow on clone), B08 (server packs).
**Estimated effort:** ~3–5 days
**Touches:** new step classes per mode, schemas, refactor of clone-family stubs into real implementations, tests.

---

## Why this brief exists

Brief B03 added the four top-level clone commands as stubs. Brief B06
made `clone` a workflow. Brief B08 added server packs. This brief turns
the stubs into real implementations:

- `sgit clone-branch` — thin clone (HEAD-rooted trees + lazy historical fetch).
- `sgit clone-headless` — online-only, no/cache `.sg_vault/`.
- `sgit clone-range <range>` — clone a commit range (PR-style).
- `clone --bare`, `clone-branch --bare`, `clone-range --bare` — no working copy variants.

Each mode is a new `Workflow__*` composing existing + new step classes.
Server pack flavours from B08 (`head`, `bare-head`, `range`) are
consumed where applicable.

---

## Required reading

1. This brief.
2. `design__01__access-modes.md` (the authoritative mode definitions).
3. `design__04__workflow-framework.md` (framework primitives).
4. `design__05__clone-pack-format.md` (per-mode pack flavours).
5. The implementations of briefs B03, B06, B08.

---

## Scope

### Mode 1 — `clone-branch` (thin)

New workflow `Workflow__Clone_Branch` composing:
1. `derive_keys`, `check_directory`, `download_index`, `download_branch_meta`, `walk_commits` — reused from B06.
2. NEW: `Step__Clone__Download_Head_Pack` — downloads the `head` pack flavour from B08.
3. NEW: `Step__Clone__Walk_Head_Tree_Only` — walks ONLY HEAD's tree (no historical roots).
4. `download_blobs` (reused), `create_clone_branch` (reused), `extract_working_copy` (reused), `setup_local_config` (reused).

Plus the **lazy historical-tree fetch path**:
- New helper `Vault__Sync.fetch_tree_lazy(tree_id)` — checks if the tree is in `bare/data/`; if not, downloads it (per-object, or via a `tree-history` pack flavour from B08 if available).
- Wire it into history-traversal commands: `sgit history log -p`, `sgit history diff <past>`, `sgit history show <commit>`, `sgit history blame`, `sgit branch switch <past-state>`.
- Each lazy fetch is logged to `.sg_vault/local/lazy-fetch.log` for observability.

### Mode 2 — `clone-headless`

New workflow `Workflow__Clone_Headless` composing:
1. `derive_keys` (reused).
2. NEW: `Step__Clone__Headless_Probe` — verifies vault exists + accessible.
3. NEW: `Step__Clone__Headless_Setup_Cache` — creates a minimal `.sg_vault/local/` (just credentials), or no on-disk state at all if `--no-cache`.

After clone, all subsequent commands work as remote calls. Helpers like
`sgit file cat <path>` against a headless vault hit the server live.

### Mode 3 — `clone-range`

New workflow `Workflow__Clone_Range` composing:
1. `derive_keys` (reused).
2. `check_directory` (reused).
3. `download_index` (reused).
4. NEW: `Step__Clone__Walk_Commit_Range` — given `<from>..<to>`, walks just those commits.
5. NEW: `Step__Clone__Download_Range_Pack` — downloads the `range` pack flavour from B08.
6. `extract_working_copy` (reused) — extracts the range tip's working copy.

CLI shape: `sgit clone-range <vault-key>:<from>..<to> <dir>`.

### `--bare` variants

For `clone --bare`, `clone-branch --bare`, `clone-range --bare`:
- Skip `Step__Clone__Extract_Working_Copy`. Workflow ends after `setup_local_config`.
- Mode flag in `Schema__Workflow__Clone__Input` controls this.

`clone-headless --bare` errors per design D1.

### Tests

- One workflow-level happy-path test per mode.
- `clone-branch` lazy-fetch tests: clone, then `history log -p`, assert lazy fetch was triggered.
- `clone-headless` test: clone, then `file cat`, assert no `bare/data/` access.
- `clone-range` test: clone a range, assert only range objects are present.
- `--bare` tests for each applicable mode.

---

## Hard constraints

- **All steps + workflows + schemas Type_Safe.**
- **No mocks.** Real in-memory transfer server.
- **No `__init__.py` under `tests/`.**
- **Behaviour:** for `clone` (full), no change from B06. For the new modes, behaviour is new but documented.
- **Coverage on new step/workflow code ≥ 85%.**
- Suite must pass under Phase B parallel CI shape.
- Each mode workflow has its own progress reporting.

---

## Acceptance criteria

- [ ] Four workflows implemented (`Workflow__Clone`, `Workflow__Clone_Branch`, `Workflow__Clone_Headless`, `Workflow__Clone_Range`).
- [ ] All four `sgit clone*` commands invoke their workflows.
- [ ] `--bare` flag honoured for the three modes that support it.
- [ ] Lazy historical-tree fetch wired into `history` commands.
- [ ] At least 4 happy-path tests + 4 lazy-fetch / mode-specific tests.
- [ ] Coverage on new code ≥ 85%.
- [ ] Suite ≥ existing test count + N passing.
- [ ] `sgit dev workflow show <command>` lists the steps for each new workflow.

---

## Out of scope

- Migration command (brief B10).
- Push / pull / fetch refactor (brief B11).
- Server-side pack builder changes for new flavours — coordinate with B08; if `range` and `bare-*` flavours weren't shipped in B08, this brief either ships them in B08 or queues a B08-followup.

---

## Deliverables

1. New workflow + step classes.
2. New schemas.
3. Lazy-fetch wiring in history commands.
4. Tests.
5. Closeout note in sprint overview.

---

## When done

Return a ≤ 300-word summary:
1. Workflows shipped + their step lists.
2. Lazy-fetch behaviour confirmed in history commands.
3. Performance numbers per mode (clone-branch vs clone, headless vs clone, range vs clone).
4. Coverage + test count deltas.
5. Anything that surfaced about server packs that needs B08 follow-up.
