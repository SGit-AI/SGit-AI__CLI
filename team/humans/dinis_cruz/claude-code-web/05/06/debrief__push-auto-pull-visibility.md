# Debrief: Push Auto-Pull Visibility

**Date:** 2026-05-06
**Author:** Explorer reviewer agent (`claude/cli-explorer-session-J3WqA`)
**Commit:** `6cb1b1d`
**Baseline:** 3,246 passed → **3,248 passed** (+2 new tests)

---

## Problem

`sgit push` silently runs a pull before uploading (fetch-first pattern, step 2 of push).
The pull result was checked only for conflicts and then discarded — no file changes
were ever printed. An agent (or human) running `commit → push` would see:

```
Pushing to default...
Push complete. Named branch updated.
  Pushed 1 commit(s), 3 object(s) uploaded.
```

…with no indication that remote files arrived during the implicit pull.
Agents reading the push output after `sgit commit && sgit push` were therefore
unaware of changed files and continued with a stale view of the working directory.

---

## Root Cause

In `Vault__Sync__Push.push()` (line 111–116 before this fix):

```python
if not first_push and not force:
    pull_result = Vault__Sync__Pull(...).pull(directory)
    if pull_result['status'] == 'conflicts':
        raise RuntimeError(...)
# pull_result never reached cmd_push — discarded here
```

`pull_result` was a local variable that never made it into the return dict.
`CLI__Vault.cmd_push()` therefore had no file-change data to print.

---

## Fix

### `sgit_ai/core/actions/push/Vault__Sync__Push.py`

1. **Initialise `pull_result = None`** before the conditional so all code paths
   have a consistent value.

2. **Add `_pull_file_changes(pull_result)`** helper method (8 lines) that extracts
   `added / modified / deleted` lists from the pull result, returning empty lists
   when the pull was skipped or was already up-to-date:

   ```python
   def _pull_file_changes(self, pull_result: dict) -> dict:
       if not pull_result or pull_result.get('status') == 'up_to_date':
           return dict(pull_added=[], pull_modified=[], pull_deleted=[])
       return dict(pull_added    = pull_result.get('added',    []),
                   pull_modified = pull_result.get('modified', []),
                   pull_deleted  = pull_result.get('deleted',  []))
   ```

3. **Spread pull fields into all post-pull return dicts** — 3 return sites:
   - `status='up_to_date'` after pull reveals nothing to push (line ~122)
   - `status='up_to_date'` for empty clone commit (line ~125)
   - `status='pushed'` main success path (line ~270)

### `sgit_ai/cli/CLI__Vault.py`

4. **Add `_print_pull_changes(push_result)`** method (16 lines) that reads
   `pull_added / pull_modified / pull_deleted` from the push result and prints
   them before the push status block. Suppressed entirely when all lists are empty.

5. **Call `_print_pull_changes(result)`** at the top of the `cmd_push` status
   block, before all `if status ==` branches.

---

## Output Before / After

**Before** (remote changes arrive during push — completely silent):
```
Pushing to default...
Push complete. Named branch updated.
  Pushed 1 commit(s), 3 object(s) uploaded.
  commit abc123...
```

**After** (same scenario):
```
Pushing to default...

Auto-pulled remote changes before push:
  + from_alice.txt
  ~ shared_config.py
  1 added, 1 modified, 0 deleted (2 total)

Push complete. Named branch updated.
  Pushed 1 commit(s), 3 object(s) uploaded.
  commit abc123...
```

When there are no remote changes the block is suppressed — no extra noise
for the common single-developer push.

---

## Files Changed

| File | Change |
|---|---|
| `sgit_ai/core/actions/push/Vault__Sync__Push.py` | `pull_result = None` init; `_pull_file_changes()` helper; pull fields in 3 return dicts |
| `sgit_ai/cli/CLI__Vault.py` | `_print_pull_changes()` method; call in `cmd_push` |
| `tests/unit/cli/test_CLI__Vault__Push.py` | 2 new tests in `Test_CLI__Vault__Push__Shows_Auto_Pull` |

---

## Tests Added

| Test | What it verifies |
|---|---|
| `test_push_shows_auto_pulled_files` | Alice pushes `from_alice.txt`; Bob commits + pushes; output contains "Auto-pulled remote changes before push:" and "from_alice.txt" |
| `test_push_silent_when_no_remote_changes` | Bob pushes with no pending remote changes; "Auto-pulled" does not appear in output |

Both tests use a real two-clone `Vault__Test_Env` setup — no mocks.

---

## What Was NOT Changed

- The fetch-first pull itself — timing, ordering, conflict-abort behaviour unchanged.
- `pushed_branch_only` path — also receives `pull_added/modified/deleted` in its
  return dict (via the same `**_pc` spread) so it could display them, but
  `_print_pull_changes` is called before the status branch so it will appear
  for that path too if there are changes.
- Force-push path (`--force`) skips the pull entirely; pull fields will be empty
  lists, so `_print_pull_changes` is suppressed.
