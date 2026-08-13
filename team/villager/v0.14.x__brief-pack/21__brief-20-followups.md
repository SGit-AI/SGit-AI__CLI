# Brief 21 — Brief 20 follow-ups (history reset --fetch + integration tests)

**Date:** 2026-05-08
**Audience:** SGit Dev Agent
**Scheduling:** small reviewer-fix-style pass after Brief 20 merges. Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)
**Source:** confirmed in production by the conductor.content agent who recovered the stuck `4wrqg006` vault on 2026-05-08; their recovery report explicitly named both gaps.

---

## 1. Why this exists

Brief 20 specified two things that didn't land in the executor's commit (`ed5189f`):

1. **`sgit history reset --fetch`** (Brief 20 §3f) — the universal escape hatch for stuck agents whose target commit isn't cached locally.
2. **5 integration tests** in `tests/integration/` (Brief 20 §7b) — particularly the bug-report repro `test_conflict_loop_can_be_aborted`.

Both are small. Both got skipped during the merge-state architectural work. The conductor agent's recovery report from today confirms they matter:

> 1. `sgit history reset` requires locally cached commit objects — but standard clones don't cache them. So the documented recovery path ("reset to parent") is unavailable after a typical clone. This needs a `--fetch` flag.
> 2. The conflict loop fix the dev team suggested (`backup → reset → pull → reapply`) required falling back to a completely fresh clone because `reset` was unavailable. That's a significant extra cost — ~15s clone time plus all the work to reapply. For larger vaults it could be much worse.

So the gap isn't theoretical. An agent in the wild had to fall back to a full re-clone (~15s plus all the reapply work) because the `reset` escape hatch wasn't usable on their post-clone state.

---

## 2. Item 1 — `sgit history reset --fetch`

### 2a. The current failure mode

`sgit history reset <commit-id>` calls `Vault__Sync__Pull.reset()` (`sgit_ai/core/actions/pull/Vault__Sync__Pull.py:17-68`). The first thing it does:

```python
try:
    target_commit = vault_commit.load_commit(commit_id, read_key)
except FileNotFoundError:
    raise RuntimeError(f'Commit not found locally: {commit_id} '
                       f'— run sgit pull to fetch missing history first')
```

The hint "run `sgit pull` to fetch missing history" is wrong in the conflict-loop scenario — `pull` is exactly what's blocked. The agent is stuck.

### 2b. The fix

Add a `--fetch` flag. When set, before the load_commit call:

```python
def reset(self, directory: str, commit_id: str = None, fetch: bool = False) -> dict:
    c = self._init_components(directory)
    ...

    if commit_id is not None and fetch and not c.obj_store.exists(commit_id):
        # Fetch the missing commit (and any objects needed to reconstruct its
        # working copy) from the named branch's server before proceeding.
        self._fetch_for_reset(c, commit_id, directory)

    try:
        target_commit = vault_commit.load_commit(commit_id, read_key)
    ...
```

`_fetch_for_reset` reuses the existing `_fetch_missing_objects` machinery from `Vault__Sync__Pull` (which post-Brief-18 walks the full reachable graph for a target commit) — but BFS-rooted at `commit_id` instead of the named ref's HEAD. After it runs, the commit + all objects needed to checkout its tree are local.

### 2c. CLI surface

```
sgit history reset <commit-id> [--fetch]
```

Update the existing reset error message to point users at the new flag:

```
Commit not found locally: obj-cas-imm-abc123
  Run with --fetch to download it from the server first:
    sgit history reset obj-cas-imm-abc123 --fetch
```

### 2d. Tests

In `tests/unit/core/actions/pull/test_Vault__Sync__Pull__Reset.py`:

1. `test_reset_to_uncached_commit_without_fetch_errors_clearly` — set up a vault, manually delete a target commit's data file, call `reset(commit_id, fetch=False)`, assert the error mentions `--fetch`.
2. `test_reset_with_fetch_downloads_missing_commit` — same setup, `reset(commit_id, fetch=True)` succeeds, working copy matches target.
3. `test_reset_fetch_downloads_full_tree_for_checkout` — target commit's tree references blobs not local, `reset --fetch` fetches them all so checkout works.
4. `test_reset_fetch_handles_already_cached_commit_no_op` — commit IS local, `--fetch` is a no-op, no extra network calls.

Plus an integration test in `tests/integration/test_History__Reset__Fetch__Integration.py`:

5. `test_reset_fetch_for_stuck_agent_against_real_server` — exact scenario: agent in conflict-loop state, the parent commit they want to reset to isn't cached, `reset --fetch <id>` recovers cleanly.

---

## 3. Item 2 — Brief 20's missing integration tests

Brief 20 §7b specified 5 integration tests against the real local SG/Send server. None landed. Add them now:

### 3a. `tests/integration/test_Conflict__Loop__Recovery__Integration.py`

```
test_conflict_loop_can_be_aborted
  - Two clones of same vault.
  - Clone A makes change to file X, commits, pushes.
  - Clone B makes conflicting change to file X, commits.
  - Clone B push → auto-pulls → conflict.
  - Clone B sgit-ac merge-abort → succeeds.
  - Clone B sgit-ac pull → clean (gets clone A's commit).

test_flow_a_capture_then_resolve_end_to_end
  - Same setup through the conflict.
  - sgit-ac commit "captured" (with .conflict files in tree) → linear commit.
  - Manually delete .conflict files (or edit the conflicted file).
  - sgit-ac commit "resolved" → 2-parent merge commit (or linear with --no-merge-commit).
  - sgit-ac push → succeeds.

test_flow_b_resolve_then_merge_commit_end_to_end
  - Same setup through the conflict.
  - sgit-ac resolve --all --ours.
  - sgit-ac commit (no message) → 2-parent merge commit auto-created.
  - sgit-ac push → succeeds.

test_push_refuses_with_conflict_files_against_real_server
  - Same setup through conflict.
  - sgit-ac push → Vault__Push_With_Conflicts_Error.
  - sgit-ac push --push-conflict → succeeds (with .conflict files in tree).

test_history_reset_fetch_for_stuck_agent
  - Same as item 2d test 5 above (or merge them — same scenario).
```

These tests use the existing `vault_api` / `temp_dir` / `crypto` fixtures from `tests/integration/conftest.py`. No new infrastructure.

---

## 4. Why this matters now

Three reasons:

1. **Real-world cost.** The conductor agent reported a 15s clone + reapply work as the recovery cost on their vault — and noted "for larger vaults it could be much worse." On a multi-GB vault, full re-clone could take minutes. `reset --fetch` collapses this to seconds (just the missing commit + tree).

2. **Verification.** Brief 20's unit tests prove the merge-state mechanics work in isolation. They DON'T prove the conflict-loop scenario is structurally impossible end-to-end against the real server. The integration tests pin that contract. Per Brief 15's standard ("every network-touching action requires an integration test"), this is the gap.

3. **Symmetry with Brief 18 + Brief 02 follow-ups.** When sgit ships a new escape hatch, agents in the field need it to actually work. Brief 18's `_try_repair_missing` covered the move case. `history reset --fetch` is the same shape for the reset case.

---

## 5. Order of work

1. **Item 1 — `--fetch` flag + 4 unit tests + 1 integration test** — ~3h.
2. **Item 2 — 4 additional integration tests** for Brief 20 — ~2h.
3. **Reviewer fix pass** — ~30min.

Total: ~½ day. Slot anywhere in the queue; doesn't block other work.

---

## 6. Verification checklist

When done:

- `sgit history reset <commit-id> --fetch` works against a server when the commit is uncached.
- The error message for an uncached commit (without `--fetch`) explicitly suggests adding the flag.
- All 5 integration tests from Brief 20 §7b are present and pass.
- A 6th integration test for `reset --fetch` is present and passes.
- All 3,450+ unit tests still pass.
- KNOWN_VIOLATIONS unchanged.

---

## 7. The takeaway for the brief discipline

Brief 20 had 14 unit tests specified and 5 integration tests specified. The implementation delivered 20 unit tests and 0 integration tests. Both decisions were locally rational (more unit-tier coverage; integration tests are slower/more setup) but together they fail the brief's verification standard.

The follow-up pattern for future briefs: when the brief specifies integration tests by name, the executor should land them or explicitly defer them with a note in the commit message. Silent omission produces exactly this kind of "we shipped the feature; the safety net wasn't proven against the real server" gap.

Worth a one-line addition to the start-here briefing: "If the brief specifies integration tests, land them or explicitly defer them in the commit message. Don't silently skip."
