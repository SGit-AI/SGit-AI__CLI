# Brief 20 — Make merge-in-progress a first-class state (conflict-loop fix)

**Date:** 2026-05-08
**Audience:** SGit Dev Agent
**Scheduling:** **🔴 URGENT.** Agents are getting permanently stuck. Lands ahead of every other pending v0.14.x brief except 16 (which is small / cosmetic). Estimated effort: ~1 day.
**Author:** Villager orchestrator (Opus)
**Source incident:** Conductor agent + @Content stuck in a conflict loop on vault `4wrqg006` on 2026-05-08; full reproduction in their bug report.

---

## 1. Why this exists

A real-world incident: two agents working on the same vault hit a conflict loop they cannot escape. Repro:

1. Agent A pulls (clean), commits locally.
2. Agent B pushes (the agents are working on the same vault from different sessions).
3. Agent A pushes → sgit auto-pulls → 3-way merge → 6 conflicts → `.conflict` files written.
4. Agent A deletes the `.conflict` files (choosing local versions).
5. `sgit status` says "nothing to commit" — there's no diff to commit.
6. Agent A pushes again → sgit auto-pulls AGAIN → recreates the same 6 conflicts.
7. The pull output says *"abort with `sgit merge-abort`"* — but **the command doesn't exist**.
8. **Permanently stuck.** No documented escape route.

This is happening because **sgit has no persistent merge-in-progress state** that other commands can detect. The internal `.sg_vault/local/merge_state.json` is written by `Step__Pull__Merge` but never read by anything else. All the workflows treat the post-conflict state as if it were a regular dirty working copy, which it is not.

The fix is making merge state first-class:

- `sgit status` shows "merge in progress" when the state file exists.
- `sgit push` and `sgit pull` refuse to run during a merge.
- `sgit merge-abort` exists and works.
- `sgit commit` (no args) finalises the merge if state exists.
- `sgit resolve <file> --ours/--theirs` is the agent-friendly per-file decision.
- `sgit history reset --fetch` lets stuck agents restore from server-side state.

Every one of the bug report's 6 proposed fixes falls out of this single architectural change.

---

## 2. The current state file (already half-built)

`sgit_ai/workflow/pull/Step__Pull__Merge.py:98-103` already writes:

```python
merge_state = dict(clone_commit_id=clone_commit_id,
                   named_commit_id=named_commit_id,
                   lca_id=lca_id, conflicts=conflicts)
merge_state_path = os.path.join(workspace.storage.local_dir(directory), 'merge_state.json')
with open(merge_state_path, 'w') as f:
    json.dump(merge_state, f, indent=2)
```

This file is the merge contract. The brief makes every other command read and respect it.

### 2a. Promote to a Type_Safe schema

`sgit_ai/schemas/merge/Schema__Merge_State.py`:

```python
class Schema__Merge_State(Type_Safe):
    schema_version    : Safe_UInt__Schema_Version = None    # 1
    ours_commit_id    : Safe_Str__Commit_Id       = None    # local HEAD pre-pull
    theirs_commit_id  : Safe_Str__Commit_Id       = None    # named-branch HEAD at pull time
    lca_id            : Safe_Str__Commit_Id       = None    # least-common ancestor
    started_at        : Safe_Str__ISO_Timestamp   = None    # when the merge began
    conflict_paths    : list[Safe_Str__File_Path]           # files still unresolved
    resolved_paths    : list[Safe_Str__File_Path]           # files explicitly resolved
```

Round-trip enforced. `Step__Pull__Merge` writes via `obj.json()`; every reader uses `Schema__Merge_State.from_json(...)`.

### 2b. State file location

`<vault>/.sg_vault/local/merge_state.json` — already correct. Single file, single source of truth.

### 2c. State transitions

```
[no merge state]
       ↓ sgit pull (3-way merge with conflicts)
       ↓ → write merge_state.json
[merge in progress, conflicts unresolved]
       ↓ sgit resolve <file> --ours/--theirs (move file from conflict_paths → resolved_paths)
       ↓ ... once all conflicts resolved ...
[merge in progress, all conflicts resolved]
       ↓ sgit commit (creates merge commit; deletes merge_state.json)
       ↓ OR sgit merge-abort (restore working copy from ours_commit_id; deletes merge_state.json)
[no merge state]
```

---

## 3. CLI surface

### 3a. New: `sgit merge-abort`

```
sgit merge-abort [<directory>]
    [--keep-conflict-files]    # debug only; default: remove .conflict files
```

Behaviour:
1. Read `merge_state.json`. If absent: error `"No merge in progress."`
2. For every path in `conflict_paths + resolved_paths`: remove the `.conflict` sibling file if present.
3. Restore the working copy from `ours_commit_id` (call existing `Vault__Sync__Pull.reset()` logic but without writing the ref — we're already at `ours_commit_id`).
4. Delete `merge_state.json`.
5. Print `"Merge aborted. Working tree restored to <ours_commit_id>"`.

### 3b. New: `sgit resolve`

```
sgit resolve <file> --ours              # keep our version, drop theirs
sgit resolve <file> --theirs            # take their version, drop ours
sgit resolve --all --ours               # resolve every conflict by keeping ours
sgit resolve --all --theirs             # resolve every conflict by taking theirs
sgit resolve --show                     # list unresolved conflicts with their paths
```

For each resolution:
1. Read `merge_state.json`.
2. Remove the `<file>.conflict` file (which currently holds the OTHER side's version).
3. If `--theirs`: also overwrite the working-copy `<file>` with the theirs version (sgit needs to keep this version available somewhere — see §4 below).
4. Move `<file>` from `conflict_paths` → `resolved_paths` in the state file.
5. If all conflicts resolved: print `"All conflicts resolved. Run 'sgit commit' to finalise the merge."`
6. Otherwise print `"<N> conflict(s) remaining: <list>"`.

### 3c. Two equally-supported resolution flows

The brief supports **both** of these workflows. The user / agent picks whichever fits their style:

#### Flow A — Capture-then-resolve (linear, agent-friendly, preferred default)

```
1. sgit pull
   → conflicts → .conflict files written + merge_state.json written
   → working tree now has both <path> (ours) and <path>.conflict (theirs)

2. sgit commit "Captured merge conflicts from named-branch <theirs[:12]>"
   → A REGULAR commit. The .conflict files are tracked as part of this commit's tree.
   → Audit trail explicitly captures "we got into a conflicted state here."
   → merge_state.json is NOT deleted yet (it tracks unresolved paths).
   → push refusal STILL applies (.conflict files present).

3. User / agent manually merges each <path> + <path>.conflict, then deletes <path>.conflict.

4. sgit commit "Resolved 6 conflicts from merge with <theirs[:12]>"
   → Another regular commit. Normal diff (deletions + edits).
   → merge_state.json deleted.
   → .conflict files gone.

5. sgit push
   → Push allowed (no .conflict files; no merge_state.json).
```

This flow keeps every step as a normal commit. **No special merge-commit semantics.** The audit trail shows the full dance — useful for agent debugging and for humans reviewing what happened.

#### Flow B — Resolve-then-merge-commit (git-style, familiar to git users)

```
1. sgit pull
   → conflicts → .conflict files written + merge_state.json written

2. User edits files; runs sgit resolve <file> --ours/--theirs OR manually deletes .conflict files.

3. sgit commit
   → Detects merge_state.json + all conflicts resolved.
   → Creates a 2-parent merge commit (parents = [ours, theirs]).
   → Default message: "Merge <theirs[:12]> into <ours[:12]>"
   → merge_state.json deleted.

4. sgit push
```

This flow produces a single merge commit with two parents, matching git's conventional shape. Compresses the history at the cost of less explicit audit.

**Both flows reach the same end state on the server.** The choice is a UX preference. The brief recommends **Flow A as the default** because:
- Each step is a normal commit; no special semantics to learn.
- Agents working autonomously can write each step as separate logged actions.
- Audit trail is clearer when reviewing what happened during a conflicted session.
- Linear history is easier to bisect and revert.

The `sgit commit` extension in §3d below detects which flow the user is in based on whether `.conflict` files are still present.

### 3d. Extended: `sgit commit` behaviour with merge state

`sgit commit` now branches based on the working-copy + state combination:

| State file | `.conflict` files | Behaviour |
|---|---|---|
| Absent | (any) | Existing behaviour: regular commit. |
| Present | Some present | **Flow A intermediate.** Allow the commit (regular shape). Track in state file which conflict paths are STILL present so subsequent commits can detect resolution. The commit captures the conflict state in audit. |
| Present | None present | **Flow B (or end of Flow A).** All conflicts resolved. By default, create a 2-parent merge commit (`parents = [ours, theirs]`) with default message `"Merge <theirs[:12]> into <ours[:12]>"`. User-supplied message overrides. Delete `merge_state.json` after success. |

Add a flag `sgit commit --no-merge-commit` for Flow A users who explicitly want their resolution commit to have a single parent (the previous capture-conflicts commit). With that flag, the merge_state.json is also deleted but the commit has only `[ours_after_capture]` as the parent — purely linear history.

### 3e. Push refuses with `.conflict` files in the working tree

A simple, fast check at the top of `sgit push`:

```python
def _check_no_conflict_files(self, directory: str) -> None:
    """Walk the working dir, refuse push if any .conflict file exists."""
    conflict_files = []
    for root, dirs, files in os.walk(directory):
        # Skip .sg_vault/ and other ignored dirs
        if '.sg_vault' in dirs:
            dirs.remove('.sg_vault')
        for f in files:
            if f.endswith('.conflict'):
                rel = os.path.relpath(os.path.join(root, f), directory)
                conflict_files.append(rel)
    if conflict_files:
        examples = ', '.join(conflict_files[:3])
        raise Vault__Push_With_Conflicts_Error(
            f'Cannot push: {len(conflict_files)} unresolved .conflict file(s) '
            f'in working tree (e.g. {examples}). '
            f"Resolve them first, or pass --push-conflict to push anyway."
        )
```

The `--push-conflict` flag bypasses this check. Use cases for the override:

- Flow A's "captured merge conflicts" commit was made; user wants to push that commit so a coworker can help resolve.
- Sharing a "stuck state" with a colleague for collaborative resolution.
- Test/debug scenarios.

`Vault__Push_With_Conflicts_Error` is a typed exception so the CLI's friendly-error path can format it specifically.

This check is **independent** of the `merge_state.json` check (§3f) — both apply at push time. A vault could legitimately have `.conflict` files without a merge state (e.g. someone manually created a file ending `.conflict`); the override flag handles that edge case. Conversely, the state file alone (without `.conflict` files) means "merge fully resolved, ready to commit" — no need to refuse push if the user has already commit-resolved.

### 3f. Pull refuses with `merge_state.json` present

`sgit pull` refuses if `merge_state.json` exists. Reusing the loop scenario:

```
$ sgit pull
error: merge in progress.
  Resolve conflicts: sgit resolve --all --ours  (keep your version)
                  or sgit resolve <file> --ours/--theirs  (per file)
                  or edit files directly + delete .conflict siblings
  Then commit:      sgit commit
  Or abort:         sgit merge-abort
```

Push refusal already covered by §3e (`.conflict` files) for the most common case. The state-file-only refusal at push time is redundant if `.conflict` files were also written; mention it in the error message regardless.

This breaks the "push → auto-pull → new conflict → push → auto-pull → new conflict" loop. Users opt INTO merge state by running `sgit pull` deliberately, never accidentally via auto-pull.

### 3e. Extended: `sgit status` surfaces merge state

When `merge_state.json` exists, `sgit status` adds at the top:

```
On branch <clone-branch-id>
Merge in progress.
  ours:    obj-cas-imm-<hash>
  theirs:  obj-cas-imm-<hash>
  lca:     obj-cas-imm-<hash>

Conflicts to resolve (5):
  library/_nav.json
  library/index.html
  ...

Resolved (1):
  library/footer.html

Use 'sgit resolve <file> --ours/--theirs' to resolve.
Use 'sgit merge-abort' to discard the merge.
```

### 3f. Extended: `sgit history reset --fetch`

Currently `history reset <commit-id>` fails if the commit isn't local with `"Object not cached locally — run sgit pull"`. For an agent stuck in a merge loop, `sgit pull` is exactly what they CAN'T do.

```
sgit history reset <commit-id> [--fetch]
```

With `--fetch`: if the commit isn't local, fetch it from the named ref's server (and any reachable parents needed for working-copy reconstruction). Then reset.

This becomes the universal "get me out of any state" escape hatch.

---

## 4. Storing "theirs" content for `--theirs` resolution

Currently `Step__Pull__Merge` writes `<path>.conflict` with the THEIRS version, leaving OURS as `<path>`. So `sgit resolve <file> --ours` is just "delete the .conflict file" (already what users do). `sgit resolve <file> --theirs` is "rename .conflict → original path."

```python
def _resolve_theirs(working_dir, rel_path):
    src = os.path.join(working_dir, rel_path + '.conflict')
    dst = os.path.join(working_dir, rel_path)
    os.replace(src, dst)   # atomic
```

For `--ours`:
```python
def _resolve_ours(working_dir, rel_path):
    conflict = os.path.join(working_dir, rel_path + '.conflict')
    if os.path.isfile(conflict):
        os.remove(conflict)
```

Both end with the same state: only `<path>` exists, with the chosen content.

---

## 5. Updated push UX (separate but related)

The bug report's Fix 3 (`--no-pull`) and the auto-pull-on-push behaviour deserve attention. Current `sgit push` always pulls first. The agent's loop hit because the auto-pull entered a 3-way-merge. Better:

`sgit push` should pull-and-fast-forward. If the pull would be a non-fast-forward (would require 3-way merge), refuse with:

```
$ sgit push
error: remote has diverged from local since last pull.
  Run 'sgit pull' explicitly to merge, then push again.
```

This makes the merge-state ENTRY explicit. The user opts in by running `pull` manually. They never get sucked into a merge they didn't ask for.

`--force` flag stays for "I really mean to overwrite" cases. `--no-pull` becomes unnecessary.

---

## 6. Implementation outline

### 6a. New files

```
sgit_ai/schemas/merge/__init__.py
sgit_ai/schemas/merge/Schema__Merge_State.py

sgit_ai/core/actions/merge/Vault__Merge__State.py    # read/write/check the state file
sgit_ai/core/actions/merge/Vault__Merge__Abort.py    # abort logic
sgit_ai/core/actions/merge/Vault__Merge__Resolve.py  # per-file resolution

sgit_ai/cli/CLI__Merge.py                            # new CLI handler for merge-abort + resolve
```

### 6b. Modified files

- `sgit_ai/workflow/pull/Step__Pull__Merge.py` — write `merge_state.json` via the schema (currently raw dict); ensure paths are saved as `Safe_Str__File_Path`.
- `sgit_ai/cli/CLI__Main.py` — register `merge-abort`, `resolve` subparsers; add merge-state check to `push`, `pull`, `commit` handler entry points.
- `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` — extend `commit()` to detect merge state and create a merge commit.
- `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` — refuse if merge state exists.
- `sgit_ai/core/actions/push/Vault__Sync__Push.py` — refuse if merge state exists; also refuse non-fast-forward auto-pulls.
- `sgit_ai/core/actions/status/Vault__Sync__Status.py` — surface merge state in the status output.
- `sgit_ai/core/actions/pull/Vault__Sync__Pull.py:reset` — accept `--fetch` flag to download missing commits from the named ref before reset.

### 6c. Where the merge-state check happens

A single helper in `Vault__Sync__Base`:

```python
def _check_no_merge_in_progress(self, directory: str, action: str) -> None:
    """Raise if a merge is in progress; called at the entry of push/pull."""
    state_path = os.path.join(directory, '.sg_vault', 'local', 'merge_state.json')
    if os.path.isfile(state_path):
        raise Vault__Merge_In_Progress_Error(
            f'Cannot {action}: merge in progress. '
            f"Use 'sgit resolve' to resolve conflicts, then 'sgit commit'. "
            f"Or 'sgit merge-abort' to discard the merge."
        )
```

`Vault__Sync__Pull.pull` and `Vault__Sync__Push.push` call it as their first action.

---

## 7. Tests

### 7a. Unit-tier (in `tests/unit/core/actions/merge/`)

1. `test_merge_state_round_trip` — `Schema__Merge_State.from_json(obj.json()) == obj`.
2. `test_merge_abort_restores_working_copy` — synthetic conflicted state; abort; assert working copy matches `ours_commit_id` tree, no `.conflict` files remain, state file deleted.
3. `test_resolve_ours_removes_conflict_file` — single-file resolve --ours; `.conflict` removed; state file's `conflict_paths` shrinks.
4. `test_resolve_theirs_replaces_working_copy` — single-file resolve --theirs; working file matches theirs version; `.conflict` removed.
5. `test_resolve_all_ours` — multiple conflicts; resolve --all --ours; all `.conflict` files removed.

**Flow A tests (capture-then-resolve, the agent-friendly default):**

6. `test_flow_a_commit_with_conflict_files_succeeds` — synthetic conflicted state; `sgit commit "captured"`; assert commit lands as a regular commit, `.conflict` files are tracked in the resulting tree, state file persists, push still refuses.
7. `test_flow_a_commit_resolution_after_manual_merge` — Flow A in two steps: capture-commit, then user manually edits + deletes `.conflict`, then commit; assert linear-history single-parent commit, state file deleted, push allowed.

**Flow B tests (resolve-then-merge-commit, git-style):**

8. `test_flow_b_commit_creates_2_parent_merge_commit` — synthetic resolved-merge state (no `.conflict` files); commit; assert resulting commit has 2 parents `[ours, theirs]`, state file deleted, default message contains both short-hashes.
9. `test_flow_b_commit_with_no_merge_commit_flag_is_linear` — same setup but with `--no-merge-commit`; assert single-parent commit.

**Refusal tests:**

10. `test_push_refuses_with_conflict_files` — `.conflict` files in working tree; push raises `Vault__Push_With_Conflicts_Error` listing the files.
11. `test_push_with_conflict_flag_bypasses_check` — same setup + `--push-conflict`; push succeeds.
12. `test_pull_refuses_with_merge_state` — state file present; pull raises `Vault__Merge_In_Progress_Error`.
13. `test_status_surfaces_merge_state` — state file present; `status()` result includes `merge_in_progress: true`, conflict counts, resolved counts.
14. `test_history_reset_with_fetch_downloads_missing_commit` — local clone missing the target commit; `reset --fetch <id>` succeeds.

### 7b. Integration-tier (in `tests/integration/`)

1. `test_conflict_loop_can_be_aborted` — the exact scenario from the bug report. Two clones; both make conflicting changes; clone A pulls and gets conflicts; `sgit merge-abort` succeeds; subsequent `sgit pull` works cleanly.
2. `test_flow_a_capture_then_resolve_end_to_end` — full Flow A: pull, capture-commit with `.conflict` files, manual edit, resolution-commit, push. Assert each step lands; final state on server is correct.
3. `test_flow_b_resolve_then_merge_commit_end_to_end` — full Flow B: pull, resolve --all --ours, commit (auto merge-commit), push.
4. `test_push_refuses_non_ff_auto_pull` — set up divergence; push refuses with the new clear error directing the user to `sgit pull`.
5. `test_history_reset_fetch_for_stuck_agent` — simulate the conductor-agent's stuck state; verify `history reset --fetch` recovers cleanly.

---

## 8. Documentation

- Update the pull-conflict output to list COMMANDS THAT EXIST (currently lies about `sgit merge-abort`):

```
CONFLICT: 6 file(s) have merge conflicts.

Quick options:
  sgit resolve --all --ours       Keep all your local versions
  sgit resolve --all --theirs     Accept all remote versions
  sgit resolve <file> --ours      Keep your version of one file
  sgit resolve <file> --theirs    Take remote's version of one file

Then:                             sgit commit
Or to abandon the merge:          sgit merge-abort
See unresolved conflicts:         sgit status  (or sgit resolve --show)
```

- Add a new section in the user docs (or README): "Resolving merge conflicts" with the standard recipe.
- Update `sgit help` text for `pull`, `push`, `commit` to mention the merge-state interaction.

---

## 9. Out of scope

- **File-level locks / advisory lock protocol.** Discussed in the bug report's Fix 5. Adds protocol surface and doesn't solve the core merge-state gap. Defer.
- **Multi-way merge** (3+ branches). Sgit's branch model is essentially clone-vs-named, so this isn't a real concern.
- **Octopus merges** (more than 2 parents). Not needed for the conductor use case.
- **Server-side conflict prevention** (e.g. CAS push refusing if remote moved). The push-refuses-non-ff path in §5 covers this client-side; server-side CAS is the SG/Send team's call.

---

## 10. Order of work

1. **Schema__Merge_State + state file read/write helpers** (~1.5h). Foundation.
2. **`sgit merge-abort` + tests** (~2h). Highest user-facing value.
3. **`sgit resolve` + tests** (~2h). The agent-friendly resolution UX.
4. **Extend `sgit commit` to finalise merge state** (~1h).
5. **Refuse pull/push during merge + status surfacing + clear errors** (~1.5h).
6. **`sgit history reset --fetch`** (~1h).
7. **Push refuses non-fast-forward auto-pull** (~30min).
8. **Documentation pass** (~30min).
9. **Reviewer fix pass** (~30min).

Total: ~10h ≈ 1 day.

---

## 11. Why this is brief 20 (urgent, jumps the queue)

Two real users (the conductor agent + @Content) are STUCK RIGHT NOW. Every other v0.14.x brief assumes vaults are usable; brief 20 ensures they remain usable when sessions overlap.

Updated landing order:
```
🔴 20 — make merge-in-progress first-class (this brief, ~1 day)
1. 16 — brief-15 cosmetic follow-ups (~1h)
2. 17 — commit-id prefix resolution (~½ day)
3. 12 — vault move cleanup pass (~½ day)
4. 09 — schema-parse error handling (~½ day)
5. 06 — dotfile tracking (~½ day)
6. 07 — .vault-settings.json + initial commit (~1 day)
7. 08 — --vault-key flag (~½ day)
8. 10 — command graph + suggestions (~1.5 days)
```

After Brief 20 + 16 + 17 + 12, the v0.14.x sprint is back on its planned track. The remaining briefs ship in the order already agreed.

---

## 12. Verification checklist

When done:

- The exact reproduction from the bug report no longer reaches a stuck state.
- `sgit merge-abort` exists, works, and the pull-conflict output references commands that exist.
- An agent can resolve all conflicts with one command (`sgit resolve --all --ours` + `sgit commit`).
- `sgit status` clearly shows merge-in-progress when present.
- `sgit pull` and `sgit push` refuse during a merge with a clear escape-route message.
- `sgit history reset --fetch` works for agents whose local clone is missing the target commit.
- All ~15 new tests pass; existing 3,450+ unit tests pass.
