# CLI Response — multi-agent legibility: architect-review fixes (round 1.5)

**To:** the analytics / `activity` session (and the two-agent `hold-coin-4916` team) + SG/Vault web team
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Companion:** `cli-response__multi-agent-legibility.md` (round 1 shipping A3 + A4 + A6)
**Architect review:** `team/explorer/architect/reviews/06/08/v0.1.0__architect-review__multi-agent-legibility-a3-a4-a6.md`

---

## TL;DR

The Explorer architect audited the A3 + A4 + A6 commit before this brief left the building and
flagged three correctness gaps. **All three are now fixed** — no regression to the core read paths,
+8 targeted tests, full suite green.

| Finding | Severity | Fixed in this round |
|---|---|---|
| **F1** A3 didn't actually work on a **read-only clone** — `Vault__Diff._init_components` hard-read `local/vault_key` which RO clones don't have | HIGH | ✅ clone-mode-aware: RO clones now use `import_read_key(read_key, vault_id)` from `clone_mode.json`; full-clone path unchanged |
| **F2** `history log --files -n 5` silently returned the **entire history**; `--graph --files` silently dropped the graph | HIGH | ✅ `-n/--limit` threaded into `log_range_with_details` (most-recent-N); `--graph` now wins over details mode and routes to the graph-capable plain log |
| **F3** A new outbound-network trigger: `history show/diff` could reach the default API host even on never-pushed local-only vaults | MEDIUM | ✅ `_on_demand_api` gated on a configured remote (`resolve_remote(...)['name'] != ''`) before building the api |
| **F5** Coverage gaps on the risky paths | MEDIUM | ✅ +8 tests: RO-clone init, wired retry through `cmd_show`/`cmd_diff`, A4 missing-base fallback, `-n` threading, `--graph` precedence, no-remote gating |

F4 (retry catches only `FileNotFoundError`, mitigated by the outer handler) and F6 (per-commit
fetch-error swallow) were graded cosmetic/acceptable for v0.1.0 — left as-is.

---

## What changed in this round

### F1 — A3 now works on read-only clones

`Vault__Diff` gained two thin helpers (`_read_clone_mode_safe`, `_resolve_keys`) so that
`_init_components` derives keys the right way for the clone's mode:

- **Full / headless clones** → unchanged: read `local/vault_key`, `derive_keys_from_vault_key(...)`
  (byte-identical to before).
- **Read-only clones** (`clone_mode.json`, `READ_ONLY`, with `read_key` + `vault_id`) →
  `crypto.import_read_key(read_key, vault_id)`. No `vault_key` ever required.

This honours the 06/04 read-only-clone contract (RO clones don't have `local/vault_key`) and
extends A3's promise to its headline use case: a collaborator on a RO clone inspecting a commit they
haven't fetched yet, without `sgit pull`.

### F2 — `-n/--limit` and `--graph` honoured

- `Vault__Diff.log_range_with_details(..., limit=N)` truncates to the most recent N commits in the
  range (oldest-first → take the tail).
- `CLI__Diff.cmd_log_range` reads `args.limit` and passes it through.
- `CLI__History._dispatch_log` precedence: **`--graph` beats details** — when `--graph` is set we
  route to the plain inspector log even if `--files`/`--patch`/`--json` is also set (the only
  command that can render a graph). The previous silent-drop is gone.

### F3 — On-demand fetch gated on a configured remote

`CLI__Diff._on_demand_api` now returns `None` immediately when `resolve_remote(...)` reports no real
remote (`name == ''`). The default `base_url` fallback in the token store is no longer enough to
trigger a network call — a never-pushed local vault stays offline. An explicit `--base-url` or a
named remote does build the api as before.

### F5 — Test additions (8 new)

`tests/unit/cli/test_CLI__Diff__Architect_Fixes.py` and
`tests/unit/cli/test_CLI__History__Log__Limit_Graph.py`:

1. RO clone has no `vault_key` on disk (contract assertion).
2. `Vault__Diff._init_components` builds keys on a RO clone (was raising `FileNotFoundError`).
3. `ensure_commit_local` works on a RO clone (the A3 headline path).
4. `_on_demand_api` returns `None` with no remote configured (F3).
5. `_on_demand_api` builds an api when `--base-url` is given (F3 positive case).
6. `cmd_show` wired retry: delete an object → re-render via on-demand fetch (real round-trip).
7. `cmd_diff` wired retry: same with commit-to-commit diff (real round-trip).
8. A4 missing-base fallback: a bogus `lca_id` triggers `(3-way view unavailable — …)` + path list,
   not a crash (the sparse-clone safety net the feature is built to tolerate).
9. `-n/--limit` threading in `--files` mode.
10. `-n/--limit` threading in `--json` mode + the no-truncation default.
11. `--graph --files` → routes to the graph-capable plain log (F2).

(That's 11 assertions; 8 distinct test methods.)

---

## What didn't change (architect confirmed safe)

- **A3 read-only / `bare/data` confinement.** The pull-path fetcher uses only `api.read` /
  `batch_read` / presigned reads; writes go through a `_save` hard-coded to `bare/data/`. No ref
  writes, no merge, no working-copy mutation. **Read-only guarantee intact.**
- **Retry control flow safety.** Every path in `cmd_diff`/`cmd_show` binds `result` before use;
  `diff_vs_*`/`diff_commits` never return `None`, so the JSON sentinel can't collide; `--remote`/
  HEAD modes don't trigger fetch (empty target list short-circuits). Uncaught retry-time
  `RuntimeError` is handled by the outer CLI exception net.
- **A4 verdict logic.** The blob-id comparison matches the merge engine's own classification
  (`Vault__Merge.three_way_merge` uses identical tests); modify/delete is `genuine` (defensible);
  SUSPECT only appears on a stale `lca_id` — the intended diagnostic. `--show` is fully read-only.
- **Zero-knowledge / crypto interop.** No new crypto operations; no new leak vector; A4 writes
  nothing to server or disk.
- **Type_Safe / project conventions.** Optional `None` defaults, no mutable defaults, no new
  module-level functions, no `@staticmethod`. Internal dict returns are consistent with the
  surrounding `Vault__Diff` code; not a new convention violation.

---

## One known characteristic worth flagging

`ensure_commit_local` walks the entire ancestry of the target commit (BFS over all parents,
`include_blobs=True`). It's functionally correct and convergent (skips objects already present), but
on a fresh sparse clone a single `history show <tip>` can pull the whole reachable history. For the
inspect-one-commit use case that's heavier than strictly necessary — a future bound (`stop_at` =
nearest cached commit, or a depth limit) would make on-demand fetch proportional to the inspection.
Not blocking; flagged in the review and tracked.

---

## Files changed in this round

- `sgit_ai/core/actions/diff/Vault__Diff.py` — `_read_clone_mode_safe`, `_resolve_keys`,
  clone-mode-aware `_init_components`; `log_range_with_details(..., limit=N)` truncates.
- `sgit_ai/cli/CLI__Diff.py` — `cmd_log_range` reads `args.limit`; `_on_demand_api` gates on a real
  configured remote.
- `sgit_ai/plugins/history/CLI__History.py` — `_dispatch_log` honours `--graph` precedence.
- `tests/unit/cli/test_CLI__Diff__Architect_Fixes.py` (new)
- `tests/unit/cli/test_CLI__History__Log__Limit_Graph.py` (new)

---

## Evidence index

- `team/explorer/architect/reviews/06/08/v0.1.0__architect-review__multi-agent-legibility-a3-a4-a6.md`
- `team/explorer/architect/reviews/06/04/v0.1.0__architect-review__read-only-clone-contract.md` (the
  RO-clone contract F1 honours)
- Round-1 brief: `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__multi-agent-legibility.md`
