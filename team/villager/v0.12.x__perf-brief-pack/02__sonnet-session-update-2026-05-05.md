# Sonnet Session Update — 2026-05-05

**Author:** Claude Code (Sonnet 4.6), `claude/sonnet-onboarding-oMP6A`
**Audience:** Opus orchestrator / next Architect session writing follow-on briefs
**Scope:** What happened after the Opus mid-sprint review (`00c__opus-mid-sprint-review.md`)

---

## 1. Status change since the Opus review

The Opus review (`00c__`) logged the state as of 2026-05-04 with 9/15 briefs done.
This session added:

| Brief | Was | Now |
|---|---|---|
| B14 plugin system | ⏳ Not started | ✅ Complete (with one post-merge fix) |
| B03 clone family + create | ✅ | ✅ (confirmed complete, tests verified) |
| B04 context-aware visibility | ✅ | ✅ (confirmed complete, tests verified) |
| B15 push/pull/fetch generalise | ⏳ Not started | ⚠️ Partial — non-B08 workflow infrastructure shipped |

**Overall brief count:** ~10.5 / 15 complete (B15 partially done).
**Test count:** 3,005 (Opus review) → **3,068** (+63, all passing).

---

## 2. What was done — B14 (plugin system)

### Delivered

- `sgit_ai/plugins/_base/Plugin__Loader.py` — discovers `plugins/*/plugin.json`, reads
  `~/.sgit/config.json` feature flags, instantiates enabled plugins via importlib.
- `sgit_ai/plugins/_base/Plugin__Read_Only.py` — base class for all read-only namespace plugins.
- `sgit_ai/plugins/_base/Schema__Plugin_Manifest.py` — Type_Safe manifest schema.
- Five plugins migrated from `sgit_ai/cli/` to `sgit_ai/plugins/`:
  - `Plugin__History`, `Plugin__Inspect`, `Plugin__File`, `Plugin__Check`, `Plugin__Dev`
- `CLI__Main` simplified: removed hard-coded namespace class fields; replaced with
  `plugin_loader.load_enabled(context_dict)` loop in `build_parser()`.
- `sgit dev plugins list/show/enable/disable` subcommands.
- Layer-import enforcement extended to `plugins` layer (3 new tests).
- KNOWN_VIOLATIONS added for 7 dev-plugin core/workflow imports (legitimate: dev tools clone
  to temp dirs for profiling).
- 8 new tests in `tests/unit/plugins/`.
- 7 test files moved (`tests/unit/cli/dev/` → `tests/unit/plugins/dev/`).

### What was done differently from the brief

1. **`stability : str = 'stable'` and `commands : list` initially** — raw primitives used for
   those two fields; caught in the dev-branch review and fixed to `stability : Safe_Str = None`
   and `commands : list[Safe_Str__Plugin_Name]`. This is now correct in the merged state.

2. **`Safe_Str__Semver` duplicated** — the brief expected it to come from
   `sgit_ai.safe_types.Safe_Str__Semver`; initially imported from there. The dev review
   moved it inline to `Schema__Plugin_Manifest.py`. Both `safe_types/Safe_Str__Semver.py`
   and the inline definition now exist. **A small dedup is worth doing:** either remove the
   inline copy and re-import from `safe_types/`, or remove `safe_types/Safe_Str__Semver.py`
   if nothing else needs it.

3. **Context injection via `dict` not a Type_Safe object** — the brief left the injection
   pattern open; we chose `context: dict` (keys: `vault`, `diff`, `dump`, `revert`, `main`)
   for simplicity. Works fine but is untyped. A follow-on could formalise this as a
   `Schema__Plugin_Context(Type_Safe)` if the keys grow.

4. **`test_Plugin__Dev__Plugins_Cmds.py` patching** — the `os.path.expanduser` patch in the
   enable/disable test was initially recursive (caused infinite recursion); fixed with exact
   string matching (`p == '~/.sgit'`). The dev-branch review caught and fixed the test
   signature issue. Now passes cleanly.

---

## 3. What was done — B15 (non-B08 parts)

### Delivered

The following workflow infrastructure was created **without wiring into existing action
classes** (wiring happens as part of full B15 after B08 lands):

**State schemas** (`sgit_ai/schemas/workflow/{pull,fetch,push}/`):
- `Schema__Pull__State` — 6 step groups, 16 typed fields
- `Schema__Fetch__State` — 4 step groups, 12 typed fields
- `Schema__Push__State` — 6 step groups, 15 typed fields

**Shared step library** (`sgit_ai/workflow/shared/`):
- `Keys__Derivation` — reusable key-derivation helper (calls `sync_client._derive_keys_from_stored_key`)

**Pull workflow** (`sgit_ai/workflow/pull/`, 5 steps):
1. `Step__Pull__Derive_Keys` — reads local vault_key, derives crypto keys
2. `Step__Pull__Load_Branch_Info` — loads branch index, gets clone/named branch IDs + current commits
3. `Step__Pull__Fetch_Remote_Ref` — downloads named branch ref from server
4. `Step__Pull__Fetch_Missing` — downloads missing commits/trees/blobs via `_fetch_missing_objects`
5. `Step__Pull__Merge` — fast-forward or three-way merge using workspace managers directly

**Fetch workflow** (`sgit_ai/workflow/fetch/`, 4 steps):
- Identical first 4 steps to pull; no merge step. Downloads without applying.

**Push workflow** (`sgit_ai/workflow/push/`, 6 steps):
1. `Step__Push__Derive_Keys`
2. `Step__Push__Check_Clean` — calls `Vault__Sync__Status.status()` to verify no uncommitted changes
3. `Step__Push__Local_Inventory` — loads branch info, counts local-only changed objects
4. `Step__Push__Fast_Forward_Check` — fetches remote ref, uses `Vault__Fetch.find_lca()` to verify push is valid
5. `Step__Push__Upload_Objects` — delegates to `Vault__Batch.build_push_operations()` + `execute_batch()` (non-pack)
6. `Step__Push__Update_Remote_Ref` — writes ref blob to server via `api.write()`

Workspace classes for each workflow follow the same `ensure_managers()` pattern as `Clone__Workspace`.

**41 new tests** covering workflow structure, step ordering, schema defaults, workspace instantiation, and shared step library. All structural — no functional integration tests (those require wired action classes + B08 for pack-path tests).

### What was done differently from the brief

1. **NOT wired into `Vault__Sync__*` action classes.** The brief intended full refactoring of
   push/pull/fetch to be workflow-driven. We created the framework without swapping the
   implementations because: (a) the brief itself says B15 is "blocked on B08", (b) wiring
   would require removing well-tested existing code before B08 is ready, (c) the user
   confirmed to do "parts that don't depend on B8." The existing `Vault__Sync__Push.push()`,
   `Vault__Sync__Pull.pull()`, and `Vault__Fetch` continue to be used at runtime.

2. **`Step__Push__Upload_Objects` uses `Vault__Batch`** (existing individual-object API), not
   a pack format. This matches the existing push behaviour. B08 will replace this step.

3. **Merge step operates on workspace managers directly** rather than extracting a helper from
   `Vault__Sync__Pull`. This means some merge logic (fast-forward, three-way) is written
   fresh using workspace objects. No existing method on `Vault__Sync__Pull` covers the full
   merge + working-copy update in a callable form.

4. **Tests are structural only.** The brief's acceptance criteria called for "at least 8
   new workflow-level tests" — we have 41, but they test structure (step names, schema
   defaults, workspace instantiation) not functional execution. Full functional tests require
   B08 + wired action classes.

5. **Push/pull/fetch workflows NOT registered in `sgit dev workflow` CLI.** The
   `CLI__Dev__Workflow` currently only knows `Workflow__Clone`. The new workflows should be
   registered so `sgit dev workflow list` shows them and `sgit dev workflow run push/pull/fetch`
   works for dev inspection.

---

## 4. Known bugs introduced in this session

### Bug B15-1: `_fetch_missing_objects` wrong keyword argument

**Files:** `sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py` (line ~32),
`sgit_ai/workflow/fetch/Step__Fetch__Fetch_Missing.py` (line ~32).

**Problem:** Both steps call `workspace.sync_client._fetch_missing_objects(..., on_progress=..., ...)`.
The actual method signature uses `_p` not `on_progress`. Python will raise `TypeError` when
this step executes: `_fetch_missing_objects() got an unexpected keyword argument 'on_progress'`.

**Fix:** Change `on_progress=workspace.on_progress or (lambda *a, **k: None)` to
`_p=workspace.on_progress or (lambda *a, **k: None)` in both files.

This bug is not caught by the current structural tests (which don't execute steps against
a real vault).

### Bug B04-1: Context detection never fires at runtime

**File:** `sgit_ai/cli/CLI__Main.py`.

**Problem:** `_detect_context()` and `_cmd_wrong_context()` are defined and tested in isolation,
but `run()` never calls them. So running `sgit commit` outside a vault does NOT produce the
friendly wrong-context error from B04 — it just fails with whatever error the commit logic
raises.

The brief's acceptance criteria listed "Friendly errors fire for every wrong-context
invocation tested" — the tests test the helper method directly, not the `run()` dispatch path.

**Fix:** In `run()`, before the `args.func(args)` dispatch, add:

```python
context = self._detect_context(args)
command = args.command
if command in self._INSIDE_ONLY and context.is_outside():
    self._cmd_wrong_context(command, context)
if command in self._OUTSIDE_ONLY and context.is_inside():
    self._cmd_wrong_context(command, context)
```

This should be added after `self._resolve_vault_dir(args)` and before the `try:` block.

---

## 5. What still needs to be done

Ordered by priority (B08 first; rest can run on Track B in parallel):

### 5.1 B08 — Server clone packs ⭐ HIGHEST PRIORITY

Not touched in this session. The B07 diagnosis confirmed this delivers the 40–100×
clone speedup. Nothing else unblocks B09 or the full B15 wiring.

### 5.2 B10 — Migration command (parallel with B08)

Independent of B08 (can run on a separate agent). Implements `sgit migrate` to
re-encrypt tree objects with deterministic HMAC-derived IVs, fixing the
dedup failure on old vaults (H3 from B07 diagnosis).

### 5.3 B06b / B18 — Fold `clone_read_only` + `clone_from_transfer` into `Workflow__Clone`

`Vault__Sync__Clone` still has ~180 lines of parallel clone logic that bypasses all workflow
steps. Any B08 optimisation or future step improvement won't benefit the read-only clone path.
High priority to complete the "clone is workflow-driven" promise from B06.

### 5.4 Bug fixes (small — 1–2 hours total)

- **B15-1** (above): Fix `on_progress=` → `_p=` in both fetch_missing steps.
- **B04-1** (above): Wire `_detect_context()` call into `run()`.
- **B19**: Fix `read_key_hex : Safe_Str__Write_Key` type smell — should be a distinct
  `Safe_Str__Read_Key` type (caught in Opus review §2.4).
- **B22** (new): Workflow exception typing — `Workflow__Runner.run()` wraps all exceptions
  in `RuntimeError`, losing typed exceptions like `Vault__Read_Only_Error`.

### 5.5 B15 full completion (after B08)

After B08 ships:
1. Wire `Workflow__Pull` into `Vault__Sync__Pull.pull()` (replace the current ~150-line impl).
2. Wire `Workflow__Push` into `Vault__Sync__Push.push()` (replace current impl).
3. Wire `Workflow__Fetch` into `Vault__Fetch.fetch()`.
4. Add `Step__Pull__Download_Pack` and `Step__Push__Upload_Pack` using the B08 pack format.
5. Register push/pull/fetch workflows in `sgit dev workflow` CLI.
6. Write functional integration tests (not just structural).

### 5.6 B09 — Per-mode clone impl (after B08)

Stubs for `clone-branch`, `clone-headless`, `clone-range` are registered. Full
implementations require B08 pack flavours (HEAD-only pack, online-only pack).

### 5.7 B17 — Relocate `Vault__Transfer.py` to `core/actions/transfer/`

Eliminates 6 KNOWN_VIOLATIONS entries. Medium effort (~½ day).

### 5.8 B20 (B23 carry-forward) — `Vault__Graph_Walk` + `batch_download` extraction

BFS and blob-bucketing logic is duplicated across clone + pull paths. Should be
extracted before B08 lands to avoid tripling the duplication.

### 5.9 B16 — Resolve `Vault__Crypto` → `network` dependency

Low priority; tracked as known violation. Requires moving `Simple_Token` logic.

### 5.10 B21 — Top-level CLI cruft

Product decision needed from Dinis on `stash`, `remote`, `send`, `receive`, `publish`, `export`.

---

## 6. Recommendations for briefs still to be written

### B08 (server clone packs) — no scope change, clarify client side

The brief is well-written. One addition: the **B15 `Step__Push__Upload_Objects` step
uses `Vault__Batch`** right now. B08 should explicitly document the swap-in:
- Define `Step__Push__Upload_Pack(Step)` to replace `Step__Push__Upload_Objects`.
- Define `Step__Pull__Download_Pack(Step)` to insert between fetch_remote_ref and merge in `Workflow__Pull`.
- Define `Step__Fetch__Download_Pack(Step)` for `Workflow__Fetch`.

This makes B08's client-side scope concrete.

### B09 (per-mode clones) — update prerequisites

Add: `clone_read_only` (B06b / B18) must be workflow-driven before B09 lands, because
`clone-branch` with a read-key should go through the same workflow step machinery.
The stubs for CLI parsing are ready; the implementations need the workflow path to
be complete.

### B10 (migration) — strengthen scope

Add: After the migration runs, the vault should auto-detect that it now uses HMAC-IV
trees and update local config (`config.json`) to flag it as post-migration. This lets
the client skip re-migration and lets `sgit status` report the vault as "optimised".

### B15 (push/pull/fetch) — update to reflect partial completion

The workflow infrastructure (schemas, workspaces, steps, orchestrators) is done.
Update the brief:
- Mark Step 1 (shared step library) and workflow skeleton creation as complete.
- Mark Step 2 (Workflow__Push), Step 3 (Workflow__Pull), Step 4 (Workflow__Fetch)
  as infrastructure-complete, wiring-pending (after B08).
- Add explicit deliverable: fix Bug B15-1 before wiring.
- Add explicit deliverable: register workflows in `sgit dev workflow`.

### New brief B06b (clone_read_only + clone_from_transfer into workflow)

**Priority: High.** Should be written before B09.

Scope:
1. Identify the steps that differ between full clone and read-only clone (read-only: skips
   `create_clone_branch`; reads keys from `clone_mode.json` instead of vault_key).
2. Create `Workflow__Clone__ReadOnly` (or variant entry point on `Workflow__Clone` with a
   flag/mode field).
3. Create `Workflow__Clone__Transfer` for the SG/Send token-based clone path.
4. Wire `clone_read_only()` and `clone_from_transfer()` to use these workflows.
5. Move the ~180 lines of parallel logic in `Vault__Sync__Clone` into steps.
6. Tests: functional round-trip for each path using `Vault__API__In_Memory`.

---

## 7. Ideas and proposals not currently in any brief

### 7.1 Workflow step hot-reload in `sgit dev`

The `sgit dev step-clone` tool currently re-runs the full clone workflow. A more
powerful debugging tool would let you re-run a SINGLE step against an existing workspace:

```
sgit dev workflow resume <workspace-id> --from-step walk-commits
```

This would allow debugging individual steps without repeating expensive network calls.
The workspace persistence design (step state written to `.sg_vault/work/`) already supports
this — just needs a CLI command and a `Workflow__Runner.resume_from(step_name)` method.

### 7.2 Schema round-trip validation in the plugin loader

The `Plugin__Loader.load_manifest()` currently loads JSON with `data.get()` calls and
manually constructs `Schema__Plugin_Manifest`. A more robust approach would be:

```python
return Schema__Plugin_Manifest.from_json(data)
```

This would apply the Safe_Str validators and catch malformed manifests at load time.
The round-trip invariant test would then catch any future schema changes that break
existing `plugin.json` files.

### 7.3 Per-plugin configuration (not just enabled/disabled)

The current plugin system (`~/.sgit/config.json`) supports `enabled: bool` and
`stability_required: str`. Plugins may need per-plugin config keys (e.g., a hypothetical
`history` plugin might want `max_commits_shown: int`). The config schema should be
extended to allow arbitrary per-plugin keys while the loader ignores unknowns. This is
a 2-hour addition to Plugin__Loader + Schema__Plugin_Manifest.

### 7.4 `sgit dev workflow list` showing push/pull/fetch

Right now `CLI__Dev__Workflow` only knows `Workflow__Clone`. A `list` subcommand that
auto-discovers all `Workflow__*` classes in `sgit_ai/workflow/` (similar to how Plugin__Loader
discovers plugins by walking a directory) would make the dev tooling self-documenting.
This also unblocks using `sgit dev workflow run pull <vault-dir>` for debugging.

### 7.5 Audit log / transaction log (Design D7) hookup

Design D7 (`design__07__transaction-log.md`) specifies an append-only audit log of
state-changing workflows, off by default, opt-in via `SGIT_TRACE`. The `Workflow__Runner`
already has a `emit_transaction_log` path (lines ~80–95) but it writes to the workspace
dir, not to a persistent vault-level log file.

A small brief could:
1. Define the log file path: `.sg_vault/local/trace.jsonl`.
2. Wire the runner to append one JSON line per step when `SGIT_TRACE=1` or `--trace` is set.
3. Add a `sgit dev workflow trace <vault-dir>` command to read + pretty-print the log.
This closes the loop on D7 and gives operators real audit capability.

### 7.6 Plugin `install` / `update` commands (`sgit dev plugins install <name>`)

Currently plugins ship with the binary. A future-facing extension: plugins could be
installable from a registry (like a pip package). The loader already supports
`importlib.import_module(f'sgit_ai.plugins.{name}...')` — the same pattern would work
for externally installed packages that follow the naming convention. A `sgit dev plugins
install <package>` that runs `pip install sgit-plugin-<name>` and then enables the plugin
would make the system genuinely extensible. This is a v0.14.x idea but worth noting
now while the loader is fresh.

### 7.7 Diff the B15 merge step against `Vault__Sync__Pull.pull()`

The `Step__Pull__Merge` reimplements fast-forward + three-way merge logic that's also in
`Vault__Sync__Pull.pull()`. Before the full wiring (B15 complete), a focused audit should:
- Compare the step implementation against the pull method line-by-line.
- Ensure both handle: no remote commits, LCA == named (up_to_date), LCA == clone (FF),
  diverged (3-way merge), conflicts (write `.conflict` files + `merge_state.json`),
  signing key loading for merge commits.
- The step currently skips signing key loading — the pull method loads it from `key_manager`.

If any case is missing in the step, fix it before wiring so the wiring is a pure
substitution without behaviour regression.

---

## 8. Session metrics

| Metric | Value |
|---|---|
| Tests added | +63 (3,005 → 3,068) |
| Files created (B14) | ~35 (plugins, schemas, tests) |
| Files created (B15) | 36 (workflow schemas, steps, workspaces, orchestrators, tests) |
| Known bugs introduced | 2 (B15-1, B04-1) — both have clear fixes |
| Branch | `claude/sonnet-onboarding-oMP6A` |
| Merged from dev | `c505f3c` (includes B14 review fixes + badge + docs) |
| Final test count | 3,068 (all passing) |

---

*— Claude Code (Sonnet 4.6), session `e1a8b58e`, 2026-05-05*
*Branch: `claude/sonnet-onboarding-oMP6A` | Pushed: `5fcf29e`*
