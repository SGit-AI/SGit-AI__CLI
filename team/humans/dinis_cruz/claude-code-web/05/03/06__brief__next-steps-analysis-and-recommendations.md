# Dev Brief: Next Steps — Analysis and Recommendations

**Version:** v0.22.17+ | **Date:** 3 May 2026
**Author:** Claude Code (SGit-AI__CLI session)
**Target team:** CLI Team (`SGit-AI__CLI`)
**Priority:** For review — no implementation started
**Depends on:** Brief 05 complete ✅

---

## Context

This brief summarises the state of `SGit-AI__CLI` after completing Brief 05
(CLI surgical-write commands) and the test coverage push to 98%. It identifies
three distinct workstreams that are ready to be picked up and proposes a
recommended sequencing.

**Current baseline:**
- 2760 unit tests, all passing
- 98% code coverage across the `sgit_ai` package
- All 22 ACs from Brief 05 satisfied
- `sgit write`, `sgit cat --id/--json`, `sgit ls --ids/--json`,
  `sgit clone --read-key`, read-only guard, `cmd_info` write-key availability,
  `cmd_derive_keys` read-key-only mode — all shipped and tested

---

## Workstream A — Brief 05 Deferred Open Questions (additive, low risk)

These items were explicitly considered in Brief 05 but deferred. They are the
lowest-friction next work: building blocks already exist, blast radius is small.

### A-1: `sgit write --delete` (OQ-2)

Remove a file from the vault tree in a single command. The agent pattern:

```bash
# Tombstone an obsolete file
sgit write content/old-hero.md ./vault --delete
→ (no blob_id; prints commit_id)
```

**Implementation:** `write_file()` already operates on the flat map. `--delete`
means removing the path from the flat map before `build_from_flat()`. ~10 lines
in `Vault__Sync__Commit.write_file()` + flag in `write_parser`.

**Why useful:** Agents that manage content vaults need a clean way to retire
content without running the full `commit` scan flow.

**Suggested ACs:**
- `sgit write path --delete` removes the file from HEAD tree and creates a commit
- `sgit ls` after `--delete` no longer shows the path
- `sgit write path --delete` on a non-existent path fails with a clear error
- `--delete` is incompatible with `--file` and stdin (fail fast if both given)
- Works on sparse clones (no full working copy required)

---

### A-2: `sgit clone --upgrade` — promote read-only to full (OQ-7)

Allow a read-only clone to be upgraded to a full clone by supplying the full
vault key, without re-downloading all blobs.

```bash
sgit clone --upgrade ./my-read-only-vault --vault-key passphrase:vaultid
→ Upgraded vault to full clone. write_key now available.
```

**Implementation:**
- Read existing `clone_mode.json` from the read-only clone
- Derive full keys from `--vault-key`, verify `vault_id` matches
- Write `vault_key` file, update `clone_mode.json` to `"mode": "full"`
- No network call, no blob re-download

**Why useful:** CI environments start with read-only clones for verification.
When a write is needed (e.g., auto-commit generated content), upgrading in-place
avoids a full re-clone of potentially large vaults.

**Suggested ACs:**
- `sgit clone --upgrade ./dir --vault-key passphrase:vault_id` succeeds when vault_id matches
- After upgrade, `sgit write` and `sgit push` work
- Upgrade fails with clear error if vault_id does not match the clone
- Upgrade fails if the clone is already a full clone
- `clone_mode.json` is updated to `"mode": "full"` after upgrade

---

### A-3: `sgit write` no-op optimisation note in `--json` output

Currently `write_file()` returns `unchanged: true` when content is identical.
The `--json` output already includes this field. However, when `--push` is
combined with `unchanged: true`, the push still runs. This is a minor UX
improvement: skip the push when `unchanged` is true.

**Implementation:** 3-line guard in `cmd_write` before the push block.

---

## Workstream B — Test Coverage: Remaining 2% (four scenario categories)

The 249 uncovered lines are documented in the coverage debrief
(`team/explorer/dev/debriefs/05/02/test-coverage-push-to-98-percent.md`).
They fall into four categories, each requiring a different testing approach.

### B-1: Merge DAG / Diamond Topology (P2 — pure unit tests possible)

| File | Lines | Scenario |
|------|-------|---------|
| `Vault__Sync__Pull.py` | 388 | BFS dedup fires when same commit reachable via two parents |
| `Vault__Sync__Clone.py` | 121, 324 | Same in clone commit-walk |
| `Vault__Merge.py` | 72–75 | 3-way merge: file deleted locally, modified remotely |

**Why actionable now:** No external services or large data needed. The test
setup requires two clones that diverge from a common ancestor and then merge.
The `Vault__Test_Env` fixture already supports `setup_two_clones()`. A merge
test class using that fixture plus a conflict-inducing edit would cover all four
lines.

**Estimated effort:** 1 focused test session, ~5 new tests.

### B-2: Race Conditions (P3 — requires concurrency harness)

| File | Lines | Scenario |
|------|-------|---------|
| `Vault__Sync__Pull.py` | 496–498 | Blob disappears between check and download |
| `Vault__Sync__Clone.py` | 408–409 | Blob disappears between list and load |

**Why harder:** Requires a `threading.Thread` that deletes objects mid-operation.
Recommend a dedicated `tests/unit/sync/test_*_Race_Conditions.py` with a
mock `obj_store.load` that introduces a timed delay.

**Estimated effort:** 1 session with concurrent testing harness design upfront.

### B-3: External Services (P2 — requires integration test environment)

| File | Lines | Scenario |
|------|-------|---------|
| `Vault__Sync__Clone.py` | 448, 452, 502–503, 518–519 | SG/Send + simple-token clone paths |

**Why deferred:** Requires live SGit-AI / SG/Send endpoints. The Python 3.12
venv integration test environment already exists
(`/tmp/sgit-ai-venv-312`). These lines are best covered by extending
`tests/integration/` rather than unit tests.

**Estimated effort:** 1 integration test session with a running `sgraph-ai-app-send`.

### B-4: Large Data / Parallelism (P3 — requires volume test fixtures)

| File | Lines | Scenario |
|------|-------|---------|
| `Vault__Sync__Clone.py` | 561–563, 578–581, 596 | >4 MB blobs, parallel chunk download |

**Why last:** Requires synthesising vaults with 5+ MB blobs. A test helper that
generates large random bytes and runs through the clone pipeline would cover all
three sub-scenarios. Self-contained but slow (~seconds per run).

---

## Workstream C — New Feature Candidates (require new briefs)

These are not yet specified. Listing them to frame the roadmap discussion.

### C-1: `sgit tag` — lightweight content tags

Agents that manage versioned content need a way to pin a specific commit as
"published" or "v1.2". Git-style lightweight tags stored as ref files in
`.sg_vault/bare/refs/tags/`. Foundation: `Vault__Ref_Manager` already handles
ref files.

### C-2: `sgit diff --remote` — diff local HEAD against named branch

Currently `sgit diff` only compares working copy against HEAD. An agent
verifying whether its local writes differ from what's on the server would
benefit from `sgit diff --remote` (compare clone HEAD against named HEAD
without pulling). All building blocks exist: `sparse_ls`, `_walk_commit_ids`,
`Vault__Diff`.

### C-3: `sgit log --json` — machine-readable commit history

Agents parsing vault history for manifest updates need structured output.
`cmd_log` currently prints formatted text. Adding `--json` flag (like `ls`
and `cat` already have) makes it scriptable. The log data is already
computed — it's a formatting change only.

### C-4: `sgit export` — dump vault content to a plain directory

Export the current HEAD tree as decrypted files to a target directory, without
setting up a full clone. Useful for CI pipelines that need vault content in a
plain filesystem without any `.sg_vault/` metadata. Similar to `git archive`.

---

## Recommended Sequencing

| Phase | Work | Rationale |
|-------|------|-----------|
| **Next** | A-1 (`--delete`), A-3 (push skip on unchanged) | Completes Brief 05 deferred items; trivial effort; high agent value |
| **Shortly after** | C-3 (`log --json`), C-2 (`diff --remote`) | Small additive changes; immediate agent utility; no new architecture |
| **Medium term** | B-1 (merge DAG coverage) | Closes the one remaining coverage gap that needs no external infrastructure |
| **Longer term** | A-2 (clone upgrade), C-1 (tags), C-4 (export) | Requires more design; higher value for multi-agent workflows |
| **Integration sprint** | B-3 (external services), B-2 (race conditions), B-4 (large data) | Coordinate with infra; run against real server |

---

## Open Questions for Review

| # | Question |
|---|---------|
| OQ-1 | Should `sgit write --delete` also push immediately when combined with `--push`? (Consistent with existing `--push` behaviour — recommend yes.) |
| OQ-2 | Should `sgit log --json` use the same output schema as `sgit ls --json`? Or a richer schema with parent IDs and signatures? |
| OQ-3 | Is `sgit clone --upgrade` the right verb, or should it be `sgit unlock` / `sgit promote`? |
| OQ-4 | Should `sgit export` preserve directory structure, or flatten to a single level? (Recommend: preserve, with optional `--flat` flag.) |
| OQ-5 | Coverage B-1 (merge DAG) — should this be done before or after C-3/C-2? Merge coverage is a correctness concern; `log --json` is a convenience feature. Recommend B-1 first. |

---

*Claude Code — SGit-AI__CLI session | 3 May 2026*
