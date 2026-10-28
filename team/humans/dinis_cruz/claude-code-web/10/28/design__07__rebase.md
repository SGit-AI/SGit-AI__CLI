# Design 07: rebase (`history rebase`, `pull --rebase`, interactive todo)

> Read with [`design__00__index-and-reconciliation.md`](design__00__index-and-reconciliation.md): where the two disagree (shared foundations F1–F9, the in-progress rules), the index wins.

**Roadmap item:** 2.12 in `roadmap__git-parity.md`, moved to priority 2 on 28 Oct 2026.
**Status:** design only. Nothing here is implemented.
**Checked against:** this repository at `4a9fcfc` (branch `claude/charming-babbage-5hzcxq`) and git 2.43.0. Git
behaviour cited as *measured* was run in a scratch repository on 28 Oct; the transcripts are summarised in 1.2.

**Depends on:**

| Doc | What this design uses from it |
|---|---|
| `design__01__line-merge-and-cherry-pick.md` | `three_way_merge(..., content_merger=, read_key=)`, `Vault__Content_Merger`, `Vault__Merge_Style_Resolver`, `Enum__Merge_Operation`, the new `Schema__Merge_State` fields, `Vault__Merge.unresolved`, `Vault__Merge_Unresolved_Error`, `write_marker_files`, `Vault__Cherry_Pick.pick_message`, `_fetch_blobs_verified`. Section 5.5 lists the exact API needed. |
| `design__02__signing-with-your-own-key.md` | `Signing__Config__Resolver`, `User__Signer`, `Schema__Signing_Flags`, `create_commit(..., user_signer=)` |
| `design__03__partial-commits-and-hooks.md` | `Vault__Hooks`, `Enum__Hook_Name`, `VERIFY_HOOKS`, `Vault__Hooks.environment` (reused for `exec`) |
| `design__05__bisect.md` | the generation-ordered painting walk in `Vault__Bisect__Graph` (proposed here to move into a shared `Vault__Commit_Graph`), `Vault__Bisect__State.check_not_in_progress` |
| `design__06__worktree.md` | nothing new; rebase state is per working copy, so it lives in each worktree's own `.sg_vault/local/` |

---

## 1. Summary and the exact Git behaviour matched

### 1.1 In one paragraph

Rebase replays **this clone's own commits that the named branch does not yet hold** on top of another commit,
usually the named branch's newest head. Each replayed commit is a cherry-pick: the change it made relative to its
parent is applied to the new tip. Merge commits in the range are dropped and the history becomes linear. Commits
whose change is already upstream are skipped. A conflict stops the rebase with the state saved; the user resolves
and runs `--continue`, or `--skip`, or `--abort` to get exactly back to where they were. `pull --rebase` fetches
(with every existing guard) and then rebases instead of merging. Interactive mode (`-i`) edits a todo list: pick,
reword, edit, squash, fixup, drop, exec. Agents give the todo as a file or JSON, with no editor.

Two sgit rules on top of Git:

1. **Rebase never rewrites a commit the server already has.** Every commit in the todo must be unreachable from
   the named head this clone holds and from the remote head it last accepted (its baseline). This is the rule
   `commit --amend` and `history undo` already use (`Vault__Sync__History_Edit.is_pushed`,
   `sgit_ai/core/actions/history/Vault__Sync__History_Edit.py:26-36`). Because of it, the next push is always a
   fast-forward of the named branch, and no other clone ever sees a rewind.
2. **A replayed commit is signed by this clone**, like every commit sgit makes. A commit signed by another clone's
   key is not replayed unless the user asks (`--allow-foreign`), because replaying would re-attribute it.

### 1.2 Git behaviour matched (git 2.43, measured where marked)

| Behaviour | Git | sgit |
|---|---|---|
| What is replayed | `git rev-list --reverse --topo-order --no-merges <upstream>..HEAD` minus patch-equivalent upstream commits. **Measured:** a local commit identical in effect to an upstream one was left out of the todo before it started (`end` = 1 with two local commits). | Same set, computed with the generation-ordered painting walk (5.4). Equivalence by plaintext content hash (5.4.3). |
| Merge commits in the range | Dropped; the commits from both sides of the merge are linearised in topological order. **Measured:** `after`, a merge of `side1`, and `mer1` became `mer1, side1, after`. | Same. `--rebase-merges` is a non-goal. |
| Commits that become empty after replay | `--empty=drop` by default (`drop`, `keep`, `ask`/`stop`). | `--empty drop|keep|stop`, default `drop`. |
| `--reapply-cherry-picks` | Off by default: patch-equivalent commits skipped. | Same flag, same default. |
| Conflict | Stops with exit 1. The file holds markers; `ours` is the upstream side (`HEAD`), `theirs` is the commit being replayed. **Measured** marker labels: `<<<<<<< HEAD` / `>>>>>>> b8e5f4f (mine1)`. | Stops with exit 1. With `--merge files` (default) the working file is the new tip's version and `<path>.conflict` holds the replayed commit's; with `--merge lines`, markers (design__01). `ours` = new tip, `theirs` = the replayed commit, as in Git. |
| State directory | `.git/rebase-merge/`: `git-rebase-todo`, `done`, `onto`, `orig-head`, `head-name`, `msgnum`, `end`, `message`, `author-script`, `stopped-sha`, `interactive`, `drop_redundant_commits`, … **Measured.** | `.sg_vault/local/rebase/state.json` (one Type_Safe document) plus the editable `todo` text file (5.3). |
| `--continue` | Commits the resolved changes with the original message (author kept), then carries on. | Same. |
| `--skip` | Drops the commit that stopped and carries on. **Measured:** skipping the conflicting `mine` left `mine2` replayed. | Same. |
| `--abort` | Restores the original branch head and working tree. **Measured** reflog line: `rebase (abort): returning to refs/heads/master`. | Same: clone ref, working copy, autostash. Reflog reason `rebase (abort)`. |
| `--quit` | Forgets the rebase, leaves HEAD and the tree as they are. | Same. |
| Reflog | **Measured:** `rebase (start): checkout up`, `rebase (pick): mine2`, `rebase (continue): mine1`, `rebase (finish): returning to refs/heads/master`. `@{1}` of the branch is the pre-rebase head. | Reflog entries carry a `reason`. The finishing entry records the **pre-rebase head as its old value**, so `history undo` after a rebase goes back to before it in one step (5.11). |
| `ORIG_HEAD` | Set to the pre-rebase head. | `.sg_vault/local/ORIG_HEAD`, resolvable by `Vault__Revision` (`history reset ORIG_HEAD`). |
| Timestamps | Author date kept, committer date new; `--reset-author-date`, `--committer-date-is-author-date`. | sgit has one `timestamp_ms` (no author/committer split). Kept by default (it is what `log` shows, like Git's author date); `--reset-date` sets it to now. |
| Author | Kept; committer is the rebaser. | The signer is the author in sgit. Own commits: unchanged identity. Foreign commits: refused unless `--allow-foreign` (decision D3). |
| Hooks (measured, `-i` with one `reword`) | `pre-rebase <upstream>`; `post-checkout <old> <onto> 1`; a reword runs `pre-commit`, `prepare-commit-msg … commit HEAD`, `commit-msg`, `post-commit`, `post-rewrite amend`; each pick runs `prepare-commit-msg … message` and `post-commit`; at the end `post-rewrite rebase` with `<old> <new>` lines on stdin. | Same set and order (5.13). |
| `--onto <newbase>`, `--keep-base` | Supported. | Supported. |
| `-x/--exec <cmd>` | Inserts `exec` after each pick; runs through the shell. | Supported; runs an **argv**, no shell by default (decision D6). |
| `--autosquash` | Moves `fixup! X` / `squash! X` under X. | Supported. |
| `--autostash` | Stashes before, pops after; on a failed pop "Your changes are safe in the stash." | Same, with `vault stash`. |
| `pull --rebase`, `pull.rebase` | `true`, `false`, `merges`, `interactive`. | `--rebase` / `--no-rebase`; per-clone `pull_rebase` = `off` or `on`. `merges` and `interactive` refused with a message (non-goals). |
| Upstream default | `@{upstream}` with `--fork-point` (reflog of the upstream). | The tracked named branch as this clone holds it (local named ref). Fork point only on an accepted rewind (5.12.3). |

---

## 2. Scope and non-goals

**In scope (v1):**

- `sgit history rebase [<upstream>]` with `--onto`, `--keep-base`, `-i`, `--todo FILE|-`, `--exec`,
  `--autosquash`, `--autostash`, `--empty`, `--reapply-cherry-picks`, `--merge`/`--conflict` (design__01),
  `--reset-date`, `--allow-foreign`, `--no-verify`, `--sign`/`--no-sign` (design__02), `--dry-run`, `--json`.
- `--continue [-m MSG]`, `--skip`, `--abort`, `--quit`, `--show-todo`, `--edit-todo`.
- Todo actions: `pick`, `reword`, `edit`, `squash`, `fixup` (with `-C`/`-c`), `drop`, `exec`, `break`.
- `sgit pull --rebase` / `--no-rebase` / `--autostash`; per-clone `pull_rebase`; push's implicit pull follows it.
- `ORIG_HEAD`; reflog reasons; `status` shows a rebase in progress.
- A tree-spine builder `Vault__Sub_Tree.apply_changes` so a replayed commit costs what it changed, not the vault.

**Non-goals (v1), each with the reason:**

| Not in v1 | Why |
|---|---|
| Rewriting commits already on the server (`--rewrite-pushed`) | It makes every other clone refuse the next pull as a rewind (by design). The deliberate path exists: `history reset` + `push --force` + `pull --accept-rewind`. Decision D2. |
| `--rebase-merges` / `pull.rebase=merges` | Needs `label`/`reset`/`merge` todo verbs and a merge replay; rarely used by agents. |
| `--root` | Rebasing the vault's first commit is a vault rewrite (`vault move` territory). |
| `--update-refs` | sgit has no stacked local branches pointing into the range. |
| Splitting a commit during `edit` (several commits between stops) | `--continue` after `edit` amends the stopped commit (5.9.1). Making several commits at an `edit` stop is a follow-up (decision D8). |
| `sgit commit` during a stop | Refused with "use `history rebase --continue`" (5.15). Git allows it; the follow-up is the same as D8. |
| A `sgit config` command | Shared with design__01 D10: the field and the flag land now, the command with the next settings need. |
| Fork point from the upstream's reflog | sgit keeps no reflog of the named ref's server history. The baseline replaces it for the one case that matters (an accepted rewind, 5.12.3). |

---

## 3. CLI surface

### 3.1 Placement (Rule 9)

- **`sgit history rebase`.** Rebase rewrites commits, and CLAUDE.md rule 9 puts "anything about commits under
  `history`" (`log`, `reset`, `reflog`, `undo`, `revert` are there: `sgit_ai/plugins/history/CLI__History.py:70-170`).
  `TOP_LEVEL_COMMANDS` (`tests/unit/cli/test_CLI__B07__Namespace_Moves.py:104-109`) does **not** change.
- **`sgit pull --rebase`.** A flag on the existing top-level daily verb, as in Git.
- `rebase` joins `"commands"` in `sgit_ai/plugins/history/plugin.json`.

Decision D1 asks whether a top-level `sgit rebase` alias is wanted. The recommendation is no: `pull --rebase` covers
the daily case, and Git users find `history rebase` by `sgit help history`.

### 3.2 `sgit history rebase`

```
sgit history rebase [<upstream>] [directory]
                    [--onto NEWBASE | --keep-base]
                    [-i | --interactive] [--todo FILE|-] [--todo-format text|json]
                    [-x CMD | --exec CMD]...
                    [--autosquash] [--autostash]
                    [--empty drop|keep|stop] [--reapply-cherry-picks]
                    [--merge files|lines] [--conflict merge|diff3]
                    [--reset-date] [--allow-foreign] [--no-verify]
                    [--sign | --no-sign] [--dry-run] [--json]
sgit history rebase --continue [-m MSG] [--json] [directory]
sgit history rebase --skip     [--json] [directory]
sgit history rebase --abort    [--json] [directory]
sgit history rebase --quit     [--json] [directory]
sgit history rebase --show-todo [--json] [directory]
sgit history rebase --edit-todo [--todo FILE|-] [directory]
```

| Flag | Default | Meaning |
|---|---|---|
| `<upstream>` | the tracked named branch as this clone holds it (local named ref, verified on the last pull) | Any revision `Vault__Revision.resolve_soft` accepts (`sgit_ai/core/actions/history/Vault__Revision.py:44`): a commit id or prefix, a tag, `HEAD~3`, `@{2}`, `ORIG_HEAD`. A **named branch name** resolves to its local named ref. |
| `--onto NEWBASE` | `<upstream>` | Replay `upstream..HEAD` on NEWBASE. |
| `--keep-base` | off | NEWBASE = merge base of upstream and HEAD (reword or squash without moving). Excludes `--onto`. |
| `-i` | off | Open the todo in the sequence editor: `SGIT_SEQUENCE_EDITOR`, then `GIT_SEQUENCE_EDITOR`, `VISUAL`, `EDITOR`, then `vi`. |
| `--todo FILE` / `--todo -` | none | Non-interactive todo: a file, or stdin. Implies interactive semantics without an editor. |
| `--todo-format` | detected: a first non-blank character `[` or `{` means json, else text | Format of `--todo`. |
| `-x CMD` | none | Add `exec CMD` after every pick (repeatable, in order). |
| `--autosquash` | off | Reorder `fixup! <subject>` / `squash! <subject>` commits under their target. |
| `--autostash` | off | `vault stash` before, `vault stash pop` after (and after `--abort`). |
| `--empty` | `drop` | A commit whose replay changes nothing: drop it, keep it (an empty commit), or stop. |
| `--reapply-cherry-picks` | off | Do not skip local commits whose change is already upstream. |
| `--merge`, `--conflict` | the clone's `merge_style` / `conflict_style` (design__01) | How a file both sides changed is merged. |
| `--reset-date` | off | Replayed commits get the current time, not the original `timestamp_ms`. |
| `--allow-foreign` | off | Replay commits signed by another clone's key, re-signed by this clone (D3). |
| `--no-verify` | off | Skip `pre-rebase` (Git's scope for rebase). |
| `--sign` / `--no-sign` | design__02's resolution | Add or omit the user signature on replayed commits. |
| `--dry-run` | off | Print the computed todo and what would be skipped; write nothing. |
| `--json` | off | One JSON object on stdout (3.6). |

`--continue -m MSG` sets the message of the commit being concluded: a conflict stop, a `reword` stop in
non-interactive mode, an `edit` stop, or the end of a squash group.

### 3.3 `sgit pull --rebase`

```
sgit pull [--rebase | --no-rebase] [--autostash] [--merge files|lines] [--conflict merge|diff3]
          [--accept-rewind] [--no-checkout] [directory]
```

- `--rebase` / `--no-rebase` override the per-clone `pull_rebase` (default `off`).
- `--autostash` only with rebase (Git's rule); with merge it is refused with a message.
- With rebase on, a pull that ends in conflicts leaves a **rebase** in progress (not a merge). The output says so
  and names `history rebase --continue` / `--abort`.

New parser lines in `sgit_ai/cli/CLI__Main.py:398-406`; `CLI__Vault.cmd_pull` (`sgit_ai/cli/CLI__Vault.py:963`)
passes `rebase=` and `autostash=`.

### 3.4 Todo formats

**Text** (Git's format, so `-i` feels familiar). File: `.sg_vault/local/rebase/todo`.

```
pick 3f9a1c2b7e01 Add the field
reword 9b2c4d5e6f70 Fix typo in README
edit 0a1b2c3d4e5f Split parser
squash 7e7e7e7e7e7e squash! Add the field
fixup -C 4c4c4c4c4c4c Better message for the fixup
drop 5d5d5d5d5d5d WIP
exec pytest -q tests/unit/schemas
break

# Rebase 1d2c3b4a5e6f..3f9a1c2b7e01 onto 1d2c3b4a5e6f (6 commands)
#
# Commands:
# p, pick <commit> = use commit
# r, reword <commit> = use commit, but edit the commit message
# e, edit <commit> = use commit, but stop for amending
# s, squash <commit> = use commit, but meld into previous commit
# f, fixup [-C | -c] <commit> = like "squash" but keep only the previous
#                    commit's message, unless -C is used, in which case
#                    keep only this commit's message; -c is same as -C but
#                    opens the editor
# x, exec <command> = run command (an argv, split like a shell would, no shell)
# b, break = stop here (continue rebase later with 'sgit history rebase --continue')
# d, drop <commit> = remove commit
#
# Lines starting with # are ignored. An empty todo aborts the rebase.
```

Rules: one action per line; the commit is any prefix of 4+ hex characters after `obj-cas-imm-` that resolves
uniquely among local commits (`Vault__Revision._commit_by_prefix`, `Vault__Revision.py:128`); the rest of a pick line
is a comment. Unknown verbs and unresolvable commits refuse the whole todo before anything is written, naming the
line.

**JSON** (agents). Same verbs; messages inline, so nothing has to stop for a reword:

```json
{
  "todo": [
    {"action": "pick",   "commit": "3f9a1c2b7e01"},
    {"action": "reword", "commit": "9b2c4d5e6f70", "message": "Fix typo in README"},
    {"action": "edit",   "commit": "0a1b2c3d4e5f"},
    {"action": "squash", "commit": "7e7e7e7e7e7e", "message": "Add the field (with its tests)"},
    {"action": "fixup",  "commit": "4c4c4c4c4c4c", "use_message": "this"},
    {"action": "drop",   "commit": "5d5d5d5d5d5d"},
    {"action": "exec",   "argv": ["pytest", "-q", "tests/unit/schemas"]},
    {"action": "break"}
  ]
}
```

A bare JSON array is accepted too. `fixup.use_message` is `previous` (default, Git's plain fixup) or `this`
(Git's `-C`). An `exec` takes `argv` (a list) or `command` (a string split with `shlex.split`). Validation is a
Type_Safe parse into `Schema__Rebase_Todo` (5.2); any error refuses before anything is written.

`reword` with no message: interactive mode opens the editor; non-interactive mode stops with reason `reword` and
waits for `--continue -m MSG`.

### 3.5 Output (plain text)

Success:
```
Rebasing 3 commit(s) of clone-7f3a onto main @ 1d2c3b4a5e6f
  pick   3f9a1c2b7e01 → 8e8e8e8e8e8e  Add the field
  skip   9b2c4d5e6f70                Fix typo in README (already upstream)
  pick   0a1b2c3d4e5f → 2b2b2b2b2b2b  Split parser
Rebased: 2 replayed, 1 skipped, 0 dropped empty. Head 2b2b2b2b2b2b (was 0a1b2c3d4e5f).
  hint: sgit push to publish; sgit history undo returns to before the rebase.
```

Stop on a conflict (`--merge files`):
```
Rebasing 3 commit(s) of clone-7f3a onto main @ 1d2c3b4a5e6f
  pick   3f9a1c2b7e01 → 8e8e8e8e8e8e  Add the field
CONFLICT applying 0a1b2c3d4e5f "Split parser" (2/3):
  src/parser.py          both changed: yours (the new base) is in the file,
                         the commit's version is in src/parser.py.conflict
Rebase stopped. Resolve each file (edit it, or sgit resolve <file> --ours/--theirs), then:
  sgit history rebase --continue      (or --skip to drop this commit, --abort to undo the whole rebase)
```

Stop on `edit`, `break`, a failed `exec` and `reword` (non-interactive) use the same layout with one reason line:
`Stopped at 0a1b2c3d4e5f "Split parser" (edit): change files, then sgit history rebase --continue [-m MSG]`;
`Stopped (break)`; `exec failed (exit 3): pytest -q tests/unit/schemas — fix, then --continue (the exec is not
re-run)`; `Stopped at 9b2c… (reword): sgit history rebase --continue -m "<new message>"`.

Abort: `Rebase aborted: head back at 0a1b2c3d4e5f, working copy restored (2 file(s) rewritten, 1 removed).`

### 3.6 Exit codes and `--json`

| Exit | When |
|---|---|
| 0 | Finished, or nothing to do ("Current branch is up to date"), or `--dry-run`, `--quit`, `--abort`, `--show-todo` succeeded |
| 1 | Stopped with a rebase in progress (conflict, edit, break, reword, exec failure), **or** refused before anything was written (sgit's convention for refusals, `CLI__Main._print_friendly_error`, `sgit_ai/cli/CLI__Main.py:1195-1218`). `--json` tells them apart through `status`. |

`--json` shape (stdout, one object; human text goes to stderr):

```json
{
  "status": "done | stopped | up_to_date | aborted | quit | refused | dry_run",
  "reason": "conflict | edit | break | reword | exec_failed | empty | missing_blob | null",
  "onto": "obj-cas-imm-…", "upstream": "obj-cas-imm-…", "orig_head": "obj-cas-imm-…",
  "head": "obj-cas-imm-…",
  "total": 3, "done": 2,
  "steps": [
    {"action": "pick", "commit": "obj-cas-imm-…", "new_commit": "obj-cas-imm-…", "result": "replayed"},
    {"action": "pick", "commit": "obj-cas-imm-…", "new_commit": null, "result": "skipped_upstream"},
    {"action": "pick", "commit": "obj-cas-imm-…", "new_commit": null, "result": "conflict"}
  ],
  "stopped_at": {"commit": "obj-cas-imm-…", "action": "pick", "subject": "Split parser"},
  "conflicts": [{"path": "src/parser.py", "kind": "whole-file", "hunks": 0}],
  "exec": {"argv": ["pytest","-q"], "exit_code": 3},
  "rewritten": [["obj-cas-imm-old", "obj-cas-imm-new"]],
  "autostash": {"stashed": true, "popped": false, "stash": "stash__1761600000000.zip"},
  "message": "human-readable one line"
}
```

`result` values: `replayed`, `skipped_upstream`, `dropped_empty`, `kept_empty`, `dropped` (todo `drop`),
`squashed`, `conflict`, `stopped`, `exec_ok`, `exec_failed`.

### 3.7 `sgit status` during a rebase

`Vault__Sync__Status.status` (`sgit_ai/core/actions/status/Vault__Sync__Status.py:216-229`) gains a `rebase_info`
block next to `merge_info`:

```
rebase_in_progress : bool
rebase_onto, rebase_orig_head, rebase_stopped_at : str
rebase_reason      : str
rebase_done, rebase_total : int
```

CLI text:
```
Rebase in progress onto 1d2c3b4a5e6f: 1 of 3 done, stopped at 0a1b2c3d4e5f "Split parser" (conflict)
  (resolve, then sgit history rebase --continue; --skip drops this commit; --abort undoes the rebase)
```

---

## 4. How the code works today

| Area | Where | What it does now (and why it matters here) |
|---|---|---|
| Pull pipeline | `sgit_ai/workflow/pull/Workflow__Pull.py:18-24` | `derive_keys → load_branch_info → fetch_remote_ref → fetch_missing → merge`. Rebase reuses the first four steps unchanged. |
| Rewind guard | `Step__Pull__Fetch_Remote_Ref.py:15-56` (`_guard_rewind`), `:102-106` | A remote head that does not descend from the accepted baseline is refused (or, with `--accept-rewind`, recorded as `workspace.rewound_from`). Nothing is written in this step. |
| Verify-then-accept | `Step__Pull__Fetch_Missing.py:26` (`require_signatures`), `:71-85` | The **only** writer of the local named ref and the baseline. Rebase never writes either. |
| Merge step | `Step__Pull__Merge.py:20-216` | FF (`:99-118`), three-way (`:119-185`, merge commit at `:181`, ref at `:182`), conflicts write `.conflict` + merge state (`:143-154`). |
| Rewind re-apply | `Step__Pull__Merge.py:245-310` (`_take_rewind`) | Already a rebase-like replay: the clone's own work since `lca(clone, rewound_from)` is re-applied onto the new head, **squashed into one commit**, and any conflict refuses. `pull --rebase` replaces this with a per-commit replay (5.12.3). |
| Working-copy write | `Step__Pull__Merge.py:218-243` (`_write_selective`), `:312-321` (`_changed_entries`), `:327-362` (`_guard_working_tree`) | Deletions first, only changed entries, selective working copies honoured, unwritable files refuse before the head moves. Rebase materialisation reuses all three (5.7). |
| Reset | `Vault__Sync__Pull.py:22-78` | Flattens the target, removes, checks out every entry, writes the clone ref. Used by `merge-abort` and `history undo`. Writes every file; rebase `--abort` uses the changed-entries path instead (5.9.3). |
| Merge state | `Vault__Merge__State.py:9` (`merge_state.json`), `:42-49` `check_not_in_progress` (called by pull `Vault__Sync__Pull.py:88`, push `Vault__Sync__Push.py:50`) | The pattern for "an operation is in progress". design__01 adds `operation` and more fields; rebase adds `operation = rebase` (5.8.1). |
| Merge abort / resolve | `Vault__Merge__Abort.py:13-39`; `Vault__Merge__Resolve.py:9-94` | Abort resets to `ours_commit_id`; resolve removes or promotes `.conflict` files. Both are reused at a rebase conflict stop; abort is redirected to the rebase abort (5.15). |
| Three-way classifier | `Vault__Merge.py:14-80` | Compares **blob ids**. Blob encryption uses a random IV (`Vault__Sub_Tree.encrypt_or_reuse_blob`, `Vault__Sub_Tree.py:517-529`), so the same content written by two clones has two blob ids and counts as "both changed differently". Rebase normalises by content hash first (5.5.3). |
| History edits | `Vault__Sync__History_Edit.py:26-36` `is_pushed`; `:39-57` `undo`; `:60-113` `revert_commit`; `:116-124` `_require_clean` | The "already on the server" rule and the clean-tree requirement, both reused. |
| Amend | `Vault__Sync__Commit.py:205-229` (`_amend_plan`) | Refuses on a pushed head or a merge; keeps parents. The `edit` stop's `--continue` follows the same rule (5.9.1). |
| Commit creation | `Vault__Commit.py:34-36` `signing_bytes`; `:42-76` `create_commit` (`timestamp_ms` parameter exists) | Rebase passes the original `timestamp_ms` and `message_enc` (5.5.6). |
| Signing key | `Vault__Sync__Commit.py:20` `_load_signing_key`, used at `:162`, `:327` | The clone key for replayed commits. |
| Ref writes and reflog | `Vault__Ref_Manager.write_ref` (`sgit_ai/storage/Vault__Ref_Manager.py:16-32`) appends `old → new` to `Vault__Reflog` (`sgit_ai/storage/Vault__Reflog.py:31-46`, `MAX_ENTRIES = 1000` at `:22`). No reason field. | Rebase adds an optional `reason` and an `old` override (5.11). |
| Baselines | `Vault__Sync__Base.py:163-283` (`_remote_baselines`, `_accepted_head` `:257`, `_write_remote_baseline` `:269`) | "Only a guarded pull or merge, an accepted rewind, or this clone's own successful push moves a baseline." Rebase moves none. |
| Revisions | `Vault__Revision.py:27` `resolve`, `:44` `resolve_soft`, `:53` `head`, `:62` `head_ref_id`, `:128` `_commit_by_prefix`, `:149` `_reflog` | Upstream, `--onto` and todo commits are resolved here; `ORIG_HEAD` is added. |
| LCA | `Vault__Fetch.find_lca` (`sgit_ai/core/actions/fetch/Vault__Fetch.py:78`) | Collects at most **200** ancestors of each side (`limit=200`). On a long history it can return a wrong or no base. Rebase uses the generation walk instead (5.4.1). |
| Generations | `Vault__Pack_Index.generation_of` (`sgit_ai/core/actions/pack/Vault__Pack_Index.py:137-156`) | Memoised in `.sg_vault/local/index/generations.json`; works on loose vaults. |
| Tree diff | `Vault__Sub_Tree.diff_trees` (`Vault__Sub_Tree.py:259-304`) | Opens only folders whose ids differ: a commit's change set at the cost of the change. |
| Tree build | `build` (`:32`), `build_from_flat` (`:105-131`), core `_build_tree_from_dir_contents` (`:556-642`), `_entry_from_flat` (`:94-103`), `_store_tree` (`:644`, deterministic encryption) | `build_from_flat` re-encrypts **every** folder (it passes no `old_tree_ids`). On 58,553 folders that is the cost a rebase must not pay per commit; hence `apply_changes` (5.6). |
| Push | `Vault__Sync__Push.push` (`Vault__Sync__Push.py:26`): implicit pull at `:177-182`, chain at `:252` (`fetch_commit_chain(..., stop_at=named_commit_id)`), named ref CAS | After a rebase the clone head descends from the named head: a fast-forward push of the new chain. |
| Branch-only push | `Vault__Sync__Push.py:634-735`, `stop_at = remote_head or local named head` at `:664` | If the clone's own server ref was pushed before a rebase, `remote_head` is no longer an ancestor and the chain walk would not stop there. Fixed in 5.16. |
| Stash | `Vault__Stash.stash` (`sgit_ai/core/actions/stash/Vault__Stash.py:27`), `pop` (`:76`) | Zip-based; reused for `--autostash`. |
| History CLI | `sgit_ai/plugins/history/CLI__History.py:70-170`, `plugin.json` | Where `rebase` is registered. |
| Status | `Vault__Sync__Status.py:216-229` | Reports merge state; gains rebase state. |

---

## 5. Design

### 5.1 Terms and invariants

| Term | Meaning |
|---|---|
| `H` / `orig_head` | This clone's head (its clone-branch ref) when the rebase starts. |
| `U` / `upstream` | The commit whose ancestors are "already upstream". Default: the local named ref of the tracked named branch. |
| `O` / `onto` | Where the replay starts. Default `U`; `--onto X`; `--keep-base` → merge base of U and H. |
| `B` | The set of baselines and held heads: `{U}` ∪ local named ref ∪ the accepted baseline for the tracked branch (`_read_remote_baseline`). |
| range | Commits reachable from `H` and from none of `B`, merges excluded. |
| `tip` | The newest commit of the rebased history so far (starts at `O`). |
| `materialized` | The commit whose tree the working copy holds (plus conflict files at a stop). |

**Invariants** (each has a test in 9):

- **I1 (never rewrite pushed history).** No commit in the todo is reachable from any commit in `B`. Checked when
  the todo is built and again for every todo commit an edited todo names.
- **I2 (local only).** A rebase writes no server object and no remote ref. Only `history rebase` and the merge-free
  rebase step of `pull --rebase` run, and the pull part writes only what a pull writes today.
- **I3 (baselines untouched).** `remote_heads.json`, `last_remote_head` and the local named ref are never written
  by the rebase engine.
- **I4 (atomic undo).** After `--abort`: clone ref == `orig_head`, working copy == tree(`orig_head`) on the paths
  the rebase touched, no state files, the autostash popped. After a finished rebase, one `history undo` restores
  `orig_head`.
- **I5 (working copy == materialized).** Outside a crash window, the working copy holds tree(`materialized`) plus
  only the conflict files of the current stop, and the clone ref == `materialized`.
- **I6 (identical trees).** A tree built by `apply_changes` has the same id as `build_from_flat` on the same
  flat map (tests compare both).
- **I7 (cost follows the change).** A replay step opens only the folders on the changed paths.

### 5.2 New types and schemas

All Type_Safe, all in the paths named; no raw primitives.

| Name | File | Kind | Definition |
|---|---|---|---|
| `Enum__Rebase_Action` | `sgit_ai/safe_types/Enum__Rebase_Action.py` | Enum | `PICK='pick'`, `REWORD='reword'`, `EDIT='edit'`, `SQUASH='squash'`, `FIXUP='fixup'`, `DROP='drop'`, `EXEC='exec'`, `BREAK='break'` |
| `Enum__Rebase_Empty` | `…/Enum__Rebase_Empty.py` | Enum | `DROP='drop'`, `KEEP='keep'`, `STOP='stop'` |
| `Enum__Rebase_Stop_Reason` | `…/Enum__Rebase_Stop_Reason.py` | Enum | `CONFLICT`, `EDIT`, `BREAK`, `REWORD`, `EXEC_FAILED`, `EMPTY`, `MISSING_BLOB` (lower-case values) |
| `Enum__Rebase_Step_Result` | `…/Enum__Rebase_Step_Result.py` | Enum | `REPLAYED`, `SKIPPED_UPSTREAM`, `DROPPED_EMPTY`, `KEPT_EMPTY`, `DROPPED`, `SQUASHED`, `CONFLICT`, `STOPPED`, `EXEC_OK`, `EXEC_FAILED` |
| `Enum__Fixup_Message` | `…/Enum__Fixup_Message.py` | Enum | `PREVIOUS='previous'`, `THIS='this'`, `THIS_EDIT='this-edit'` |
| `Enum__Pull_Rebase` | `…/Enum__Pull_Rebase.py` | Enum | `OFF='off'`, `ON='on'` |
| `Safe_Str__Rebase_Message` | `…/Safe_Str__Rebase_Message.py` | Safe_Str | Commit message text: `max_length = 65536`, newlines allowed, NUL refused (`regex` replaces `\x00`), `trim_whitespace = False`, `allow_empty = True` |
| `Safe_Str__Exec_Arg` | `…/Safe_Str__Exec_Arg.py` | Safe_Str | One argv element: `max_length = 4096`, NUL refused, everything else verbatim |
| `Safe_UInt__Rebase_Step` | `…/Safe_UInt__Rebase_Step.py` | Safe_UInt | A todo index |
| `Schema__Rebase_Todo_Item` | `sgit_ai/schemas/rebase/Schema__Rebase_Todo_Item.py` | Type_Safe | `action : Enum__Rebase_Action`, `commit_id : Safe_Str__Commit_Id = None`, `message : Safe_Str__Rebase_Message = None`, `use_message : Enum__Fixup_Message = None`, `argv : list[Safe_Str__Exec_Arg]` |
| `Schema__Rebase_Todo` | `…/Schema__Rebase_Todo.py` | Type_Safe | `items : list[Schema__Rebase_Todo_Item]` |
| `Schema__Rebase_Done_Item` | `…/Schema__Rebase_Done_Item.py` | Type_Safe | `item : Schema__Rebase_Todo_Item`, `result : Enum__Rebase_Step_Result`, `new_commit_id : Safe_Str__Commit_Id = None` |
| `Schema__Rebase_Rewrite` | `…/Schema__Rebase_Rewrite.py` | Type_Safe | `old_commit_id`, `new_commit_id : Safe_Str__Commit_Id` (for `post-rewrite` and `--json`) |
| `Schema__Rebase_State` | `…/Schema__Rebase_State.py` | Type_Safe | below |

```python
class Schema__Rebase_State(Type_Safe):
    schema_version     : Safe_UInt__Vault_Version  = None   # 1
    started_at         : Timestamp_Now             = None
    clone_branch_id    : Safe_Str__Branch_Id       = None   # whose ref this rebase moves
    clone_ref_id       : Safe_Str__Ref_Id          = None
    named_branch_name  : Safe_Str__Branch_Name     = None   # display only
    orig_head          : Safe_Str__Commit_Id       = None   # H
    upstream           : Safe_Str__Commit_Id       = None   # U
    onto               : Safe_Str__Commit_Id       = None   # O
    held_heads         : list[Safe_Str__Commit_Id]          # B, for re-checking I1 on an edited todo
    tip                : Safe_Str__Commit_Id       = None   # newest rebased commit so far
    materialized       : Safe_Str__Commit_Id       = None   # what the working copy and the clone ref hold
    materializing_to   : Safe_Str__Commit_Id       = None   # set while the working copy is being written (5.7)
    todo               : list[Schema__Rebase_Todo_Item]
    done               : list[Schema__Rebase_Done_Item]
    total              : Safe_UInt__Rebase_Step
    rewritten          : list[Schema__Rebase_Rewrite]
    stopped_reason     : Enum__Rebase_Stop_Reason  = None
    stopped_item       : Schema__Rebase_Todo_Item  = None
    squash_base        : Safe_Str__Commit_Id       = None   # parent of the squash group being built
    squash_messages    : list[Safe_Str__Rebase_Message]     # messages collected so far in a squash group
    interactive        : bool                      = False
    empty              : Enum__Rebase_Empty        = None   # None = drop
    reapply_cherry_picks : bool                    = False
    reset_date         : bool                      = False
    allow_foreign      : bool                      = False
    merge_style        : Enum__Merge_Style         = None   # design__01
    conflict_style     : Enum__Conflict_Style      = None
    signing            : Schema__Signing_Flags     = None   # design__02
    autostash          : Safe_Str__File_Path       = None   # the stash zip name, when one was made
    from_pull          : bool                      = False  # started by pull --rebase (output wording only)
```

Additions to existing schemas (all optional; older builds load newer files and the reverse, because
`Type_Safe.from_json` accepts unknown keys and missing fields, verified on `Schema__Object_Commit`):

| Schema | Field | Purpose |
|---|---|---|
| `Schema__Local_Config` (`sgit_ai/schemas/Schema__Local_Config.py:9-22`) | `pull_rebase : Enum__Pull_Rebase = None` | Git's `pull.rebase`; `None` = off |
| | `rebase_autostash : bool = False` | Git's `rebase.autoStash` |
| `Schema__Reflog_Entry` (`sgit_ai/schemas/Schema__Reflog_Entry.py`) | `reason : Safe_Str__Reflog_Reason = None` | `rebase (start)`, `rebase (pick): <subject>`, `rebase (finish)`, `rebase (abort)`; `history reflog` prints it |
| `Enum__Merge_Operation` (design__01) | `REBASE='rebase'` | A conflict stop writes merge state with this operation |
| `Enum__Hook_Name` (design__03) | `PRE_REBASE='pre-rebase'`, `POST_REWRITE='post-rewrite'` | 5.13 |

New `Safe_Str__Reflog_Reason`: printable, `max_length = 200`, newlines replaced.

### 5.3 State files and persistence

```
.sg_vault/local/rebase/
    state.json      Schema__Rebase_State (0600, Vault__Secret_File: unique temp file, fsync, rename)
    todo            the editable text todo (0600), written for -i / --edit-todo / --show-todo
    message         the message being edited for reword/squash (0600), like Git's COMMIT_EDITMSG
.sg_vault/local/ORIG_HEAD     one commit id (0600)
.sg_vault/local/merge_state.json   only during a conflict stop (operation = rebase)
```

New class `Vault__Rebase__State(Type_Safe)` in `sgit_ai/core/actions/rebase/Vault__Rebase__State.py`, modelled on
`Vault__Merge__State` (`Vault__Merge__State.py:12-49`):

| Method | Behaviour |
|---|---|
| `dir_path(directory) -> str` | `<local>/rebase` |
| `exists(directory) -> bool` | `state.json` exists |
| `read(directory) -> Schema__Rebase_State` | Parses; a damaged file raises `Vault__Rebase_Error` naming the file and the remedies `--abort` (needs `orig_head`, so it is read leniently first) and `--quit` |
| `write(directory, state)` | Atomic (temp + fsync + rename), 0600 |
| `delete(directory)` | Removes the folder |
| `check_not_in_progress(directory, action)` | Raises `Vault__Rebase_In_Progress_Error`: `Cannot <action>: a rebase is in progress (<done>/<total>, stopped at <id>). Finish it with 'sgit history rebase --continue' or undo it with '--abort'.` |

Every mutation follows **write-ahead order**: create objects (immutable, harmless if orphaned) → write state →
write working copy → write the clone ref → update state (`materialized`). A crash at any point leaves a state from
which `--continue` or `--abort` is correct (5.7.3).

### 5.4 Building the todo

New class `Vault__Rebase__Planner(Type_Safe)` in `sgit_ai/core/actions/rebase/Vault__Rebase__Planner.py`.

#### 5.4.1 The range

`plan(directory, c, upstream_spec, onto_spec, keep_base, reapply, allow_foreign) -> Schema__Rebase_Plan`

1. **Resolve.** `H` = clone ref (`Vault__Revision.head`). `U` = `resolve_soft(upstream_spec)`, or the local named
   ref of the tracked named branch (`branch_manager.tracked_named_branch` as in `is_pushed`,
   `Vault__Sync__History_Edit.py:30-34`). No upstream and no argument: refuse ("this clone has never pulled its
   named branch: name a commit to rebase onto").
2. **Held heads `B`** = {U, local named ref, `_read_remote_baseline(tracked named ref)`} minus empty.
3. **Range walk.** A generation-ordered painting walk, Git's `paint_down_to_common` with generation numbers instead
   of commit dates (sgit timestamps are not monotonic once rebased commits keep their dates):
   - a max-heap of `(generation, commit_id)` seeded with `H` (flag `OURS`) and each of `B` (flag `HELD`);
   - pop the highest generation; if it carries `HELD`, propagate `HELD` to its parents; else propagate `OURS`;
     a commit reached with both flags is `HELD`;
   - stop when every entry still in the heap is `HELD` (all "stale");
   - the range is every popped commit flagged `OURS` only;
   - generations come from `Vault__Pack_Index.generation_of` (`Vault__Pack_Index.py:137`), memoised per clone, so
     the walk is exact on loose and pack vaults and costs one commit decrypt per commit once per clone.

   This walk is the one design__05 specifies in `Vault__Bisect__Graph.candidates` (`design__05__bisect.md:277-283`).
   **Proposal (decision D9):** move it into `sgit_ai/core/actions/history/Vault__Commit_Graph.py`
   (`parents`, `generation`, `paint(include, exclude) -> dict`, `range(include, exclude) -> list`,
   `merge_bases(a, b) -> list`) and have bisect and rebase both use it. The existing `find_lca` (200-ancestor limit,
   4 above) is not used.
4. **Shallow boundaries.** A boundary commit (`Vault__Scope.boundary_ids()`) has no local parents: the walk stops
   there. If the `OURS` side reaches a boundary that the `HELD` side never reached, the range cannot be proven
   (part of it may be upstream): refuse with "this shallow clone does not hold enough history to tell your commits
   from the upstream's; sgit fetch --unshallow". An unpushed range that sits wholly above the boundary always meets
   the held side first.
5. **Order.** Topological, oldest first, ties by generation then by `timestamp_ms` then id (Git's
   `--reverse --topo-order`).
6. **Merges.** Drop commits with more than one parent (Git's default; `result = dropped` is not recorded for them:
   they are simply not in the todo, as in Git).
7. **`--keep-base`.** `O` = the single merge base of U and H (`Vault__Commit_Graph.merge_bases`); several bases:
   refuse naming them.
8. **Up to date.** If the range is empty and `O` is an ancestor of `H` (or equal), the result is `up_to_date`:
   "Current head <H> is up to date." Exit 0, nothing written.
9. **Fast-forward.** If the range is empty and `H` is an ancestor of `O`: move to `O` (no replay; reflog
   `rebase (finish)`), like Git's "Fast-forwarded".

#### 5.4.2 Checks on every todo commit (also re-run on an edited todo)

| Check | Rule | Refusal text |
|---|---|---|
| I1 pushed | `Vault__Commit_Graph` painting from `B`: the commit must not be `HELD` | `<id> is already on the server (the named branch holds it); a rebase only rewrites commits that are not pushed. To undo a pushed commit for everyone: sgit history revert --as-commit --commit <id>.` |
| Local | The commit object and its first parent's tree are local (`obj_store.exists`) | `<id> is not in this clone (sgit fetch first)` |
| Foreign | `commit.author_key_id` (or, for older commits, the branch index mapping, as `Vault__Signatures._key_for` does, `sgit_ai/core/actions/verify/Vault__Signatures.py:28-39`) equals this clone's public key id, **or** `--allow-foreign` | `<id> was written by another clone (key <kid>); replaying it would sign it as this clone. Merge instead, or pass --allow-foreign to re-sign it.` |
| Scope | On a scoped clone, the commit's change set (5.5.1) is inside the held folders (`Vault__Scope.paths_outside`) | `<id> changes folders this clone does not hold (<paths>); rebase it from a full clone or widen this one (sgit fetch <folder>)` |
| Signature policy | With `signatures-required`, a foreign commit must verify (`Vault__Signatures.status_of == VERIFIED`) before it is re-signed: the user must not launder an unsigned commit through a rebase | `<id> is <status>; this vault requires signed commits` |

#### 5.4.3 Skipping commits already upstream (`--reapply-cherry-picks` off)

Git compares patch ids. sgit compares **change signatures**, computed from the plaintext content hashes that tree
entries already carry (`content_hash` = `sha256(plaintext)[:12]`, design__01 4):

```
signature(c) = sorted( (path, old content_hash or '-', new content_hash or '-') for each changed path )
             where the change set is Vault__Sub_Tree.diff_trees(c.tree, c.parent.tree)
```

- Upstream side: every non-merge commit reachable from `U` and not from `H` (the `HELD`-only commits the painting
  walk popped above the merge base). Capped at `REBASE_CHERRY_SCAN_MAX = 2000` commits; beyond it detection is
  skipped with one warning line, and step 5.5.5 (empty after replay) still drops the duplicates that apply cleanly.
- A local commit whose signature is in the upstream set gets `result = skipped_upstream` and is left out of the
  todo (it appears in `--dry-run` and `--json` output).
- Including the old hash is stricter than Git's patch id (Git ignores the context lines). A change that is "the same
  edit on a different base" is not detected here, and is caught by the empty check if it applies to nothing.

#### 5.4.4 Interactive and file todos

- `-i`: write `todo` (3.4 format, comments included), run the editor (argv from `shlex.split` of the editor
  variable, plus the file path; no shell; inherited stdio; cwd = vault root), parse. Empty todo → abort quietly
  ("Nothing to do"), as Git does.
- `--todo FILE|-`: parse text or JSON (3.4). Refusals happen before the state exists.
- `--autosquash`: for each commit whose subject starts `fixup! ` or `squash! `, move it after the last earlier
  commit whose subject equals (or starts with) the rest, turning `pick` into `fixup`/`squash`. Done before the
  editor opens, as in Git.
- `--exec`: append `exec` items after each `pick`/`reword`/`edit`/squash group.
- `--edit-todo` during a stop: rewrite the remaining todo (editor or `--todo`); checks of 5.4.2 re-run on the new
  items; `done` is untouched.

### 5.5 Replaying one commit

New class `Vault__Rebase__Replay(Type_Safe)` in `sgit_ai/core/actions/rebase/Vault__Rebase__Replay.py`.
`replay(c, state, item, tip) -> Schema__Rebase_Replay_Result` with
`result : Enum__Rebase_Step_Result`, `new_tree_id`, `changes : dict` (see below), `conflicts`,
`marker_conflicts`, `line_merged`.

Let `C` be the commit, `P` its first (only) parent, `T` the current tip.

#### 5.5.1 The change set

`delta = Vault__Sub_Tree.diff_trees(C.tree_id, P.tree_id, read_key)` (`Vault__Sub_Tree.py:259`). It returns
`added`, `deleted`, `modified` by walking only the folders whose ids differ (I7). `paths = added ∪ deleted ∪
modified`.

On a pack vault whose commit index is present and verified, the commit index's change-list member gives the same
set without a walk (`Vault__Pack_Index__Reader`); this is an optimisation behind the same interface, not a
requirement.

#### 5.5.2 The three sub-maps

For each `p` in `paths`:

- `base[p]`: the entry in `P` (from `delta`: the old side of modified/deleted; absent for added);
- `theirs[p]`: the entry in `C` (new side of modified/added; absent for deleted);
- `ours[p]`: the entry at `p` in `T`, read with a new `Vault__Sub_Tree.entry_at(tree_id, path, read_key) -> dict`
  (a sibling of `resolve_path_target`, `Vault__Sub_Tree.py:437-467`, returning the flat entry dict or `None`, with
  a per-replay folder cache so siblings share loads).

#### 5.5.3 Normalising equal content

Before classifying, for each `p` where `ours[p]` and `theirs[p]` (or `base[p]`) exist with **equal `content_hash`
and equal size** but different `blob_id`: rewrite the `blob_id` of the later side to the earlier side's id
(`theirs[p].blob_id = ours[p].blob_id`; `base` likewise). The random-IV blob encryption (4) otherwise makes "both
sides made the same change" a conflict. This lives in `Vault__Rebase__Replay._unify_equal_content` and is proposed to
design__01 for `three_way_merge` itself (cross-doc item X1, 11).

#### 5.5.4 Classify and merge (the API needed from design__01)

```
merge = Vault__Merge(crypto=…).three_way_merge(base, ours, theirs,
                                               content_merger=merger_or_None, read_key=read_key)
```

with the restricted maps above. The classifier is per path (`Vault__Merge.py:19-78`), so restricting the maps to the
changed paths gives exactly the result of the full maps on those paths, and paths outside `delta` keep `T`'s
entries. Required from design__01:

| Needed | design__01 name | Notes |
|---|---|---|
| Per-path three-way classification with an optional content merger | `three_way_merge(base_map, ours_map, theirs_map, content_merger=None, read_key=None)` returning `merged_map`, `conflicts`, `added`, `modified`, `deleted`, `line_merged`, `marker_conflicts`, `fallbacks` | Called with restricted maps |
| A merger built for the clone's style and the stop labels | `Vault__Content_Merger` + `Vault__Merge_Style_Resolver.resolve(flag, local_config)` | Labels: ours `rebase onto <O short>` / new tip, theirs `<C short> (<subject>)`, both through `Safe_Str__Conflict_Label` |
| Missing-blob fetch, verified | `Vault__Sync__Base._fetch_blobs_verified(directory, blob_ids)` | Only on sparse/selective clones (7) |
| Writing conflict files | `write_conflict_files(..., skip=)` and `write_marker_files(...)` | At a stop only |
| The unresolved check | `Vault__Merge.unresolved(directory, state, seen)` + `Vault__Merge_Unresolved_Error` | At `--continue` |
| The pick message | `Vault__Cherry_Pick.pick_message(P, record_origin=False)` | Decrypt-or-fallback of the message |

If design__01 changes a name, design__01 wins; this table is the contract.

**Folder/file collisions.** The classifier does not see that an added file `a/b` collides with a file `a` in `T`,
or an added file `a` with a folder `a/…` in `T`. `Vault__Rebase__Replay._df_conflicts(T, merged)` checks, for each
path being added: no ancestor prefix is a file in `T` (one `entry_at` per prefix, cached), and the path is not a
folder in `T` (`resolve_path_target` returns `tree`). A collision is a whole-file conflict on that path, reported
as `kind = folder-file`.

#### 5.5.5 Results

- **Conflicts** (`merge.conflicts` or folder/file collisions) → stop with reason `CONFLICT` (5.8).
- **Empty**: every `merged_map[p]` equals `ours[p]` by `content_hash` (and deletions match), meaning the change is
  already in `T`. With `--empty drop` (default): `result = dropped_empty`, the tip does not move. `keep`: create a
  commit with `T`'s tree. `stop`: stop with reason `EMPTY` (`--continue` drops it, `--continue --keep-empty`
  keeps it; decision-free, Git's `ask`).
- **Clean**: `changes = {p: merged_map.get(p)}` for every `p` in `paths` (`None` = delete) →
  `new_tree_id = Vault__Sub_Tree.apply_changes(T.tree_id, changes, read_key)` (5.6). On a scoped clone the spine
  folders are held, out-of-scope siblings are carried inside the loaded trees by id, so no `opaque` map is needed.

#### 5.5.6 Creating the replayed commit

```
Vault__Commit.create_commit(read_key      = read_key,
                            tree_id       = new_tree_id,
                            parent_ids    = [T],
                            message_enc   = C.message_enc        # unchanged bytes unless reworded or squashed
                                            if not new_message else None,
                            message       = new_message or '',
                            branch_id     = state.clone_branch_id,
                            timestamp_ms  = C.timestamp_ms if not state.reset_date else None,
                            signing_key   = clone_key,          # Vault__Sync__Commit._load_signing_key
                            author_key_id = clone_public_key_id,
                            user_signer   = user_signer)        # design__02, if resolved on
```

- `message_enc` is reused verbatim: same read key, so the replayed commit's message is the original ciphertext. A
  reworded or squashed message is encrypted fresh (`encrypt_metadata`, `Vault__Commit.py:59-60`).
- `branch_id` is this clone's branch: a replayed commit is this clone's commit.
- A commit created with an unchanged tree and parent and an identical timestamp would still differ in its signature
  bytes only if the signer is non-deterministic (ECDSA is), so ids of replayed commits are never reused by accident.
- `rewritten.append((C, new))`.

### 5.6 `Vault__Sub_Tree.apply_changes` (the spine rebuild)

`apply_changes(root_tree_id: str, changes: dict, read_key: bytes) -> str` in `sgit_ai/storage/Vault__Sub_Tree.py`.
`changes` maps a vault path to a flat entry dict (add or replace) or `None` (delete).

1. Group paths by parent folder; collect the set of affected folders = every ancestor of every changed path,
   including `''` (the root).
2. Load the affected folders that exist in the old tree, top-down along each path, with `_load_tree_entries`
   (`Vault__Sub_Tree.py:326`): decrypt each entry name once (`_entries_by_name`, `:306`). Missing folders (a new
   folder) start empty.
3. Process affected folders **deepest first**:
   - for each changed file in the folder: set `entries[name] = _entry_from_flat(name, entry, read_key)`
     (`:94-103`), or delete it;
   - for each affected child folder: replace its entry with `tree_id = new id`, or delete the entry if the child
     became empty;
   - a folder with no entries left is **not stored** (its parent drops it). The builder never creates an empty
     folder, so ids still match;
   - order the entries exactly as `_build_tree_from_dir_contents` does (`:556-642`): files sorted by plaintext name,
     then folders sorted by plaintext name. Entries carried from the old tree keep their exact encrypted bytes,
     including out-of-scope siblings on a scoped clone;
   - `new_id = _store_tree(Schema__Object_Tree(schema='tree_v1', entries=…), read_key)` (`:644`, deterministic
     encryption, so the id is a content address).
4. Return the new root id. If no change altered anything, return `root_tree_id` unchanged.

**Equivalence (I6).** For any tree `T` and change map `Δ`:
`apply_changes(T, Δ) == build_from_flat(flatten(T) ⊕ Δ)`. Tested with randomised trees (9.2). The fields that make
up an entry (`name_enc`, `size_enc`, `content_hash_enc`, `content_type_enc` with the same fallback, `large`) come
from the one helper `_entry_from_flat`, so the bytes are identical. Folder entries carry only `tree_id` and
`name_enc`, as the builder writes them (`:610-614`).

**Use elsewhere.** design__01's cherry-pick and `history revert --as-commit` can use it too (follow-up; not
required for this design).

### 5.7 The working copy: lazy, idempotent materialisation

New class `Vault__Rebase__Working_Copy(Type_Safe)` in `sgit_ai/core/actions/rebase/Vault__Rebase__Working_Copy.py`.

**Why lazy.** A rebase of ten commits that never stops does not need the ten intermediate working copies. The
working copy and the clone ref move only when the user can see them: at a stop, before an `exec`, at the end, and
on abort. On the 76,000-file vault this turns ten checkouts into one (8).

`materialize(directory, c, state, target) -> dict`:

1. If `target == state.materialized` and `state.materializing_to` is empty: return.
2. `state.materializing_to = target`; write state.
3. `change = diff_trees(target.tree, materialized.tree)` → `apply_map` = added + modified (new side),
   deletions = deleted.
4. **Guard** (only blocked targets; the tree was clean at start): `Vault__Pull__Guard.blocked_targets(directory,
   writes, deletions)` (`Vault__Pull__Guard.py`): an untracked or ignored file in the way refuses, naming it.
   Uncommitted edits at a stop (the user edited during `edit`/`break`) are handled by `--continue` before any
   materialisation, so they are never overwritten here.
5. Write through the same code pull uses: the extracted `Vault__Working_Copy__Writer.write(directory, read_key,
   selective, ours_map=materialized side, new_map=target side, apply_map)`. That is `Step__Pull__Merge._write_selective`
   (`Step__Pull__Merge.py:218-230`) moved into `sgit_ai/core/actions/checkout/Vault__Working_Copy__Writer.py` so
   pull, cherry-pick and rebase share it: deletions first, selective split, `_refuse_unwritten` on failure. The
   maps are the **changed paths only** (never full flattens).
6. `ref_manager.write_ref(clone_ref_id, target, read_key, reason=…, reflog_old=…)` (5.11).
7. `state.materialized = target`, `state.materializing_to = None`; write state.
8. Seed the scan cache for written files (every working-copy write sgit makes does; CHANGELOG 0.26.0 "Fixed — from
   the newsroom's first morning").

**Crash recovery (5.3 order).** Any `history rebase` invocation first calls `recover(directory, state)`: if
`materializing_to` is set, re-run steps 3–7 with the same target. The diff is from `materialized` (what the disk held
before) to `materializing_to`, and each write is idempotent (a file already at the target content is rewritten with
the same bytes; a deletion of an absent file is a no-op), so a half-written working copy converges. If the clone ref
already equals `materializing_to`, step 6 is a no-op.

**Selective working copies** (`clone --no-checkout` / `--sparse`, `Pull__Selective`): the writer writes only
checked-out paths and records the rest. At the end of a `pull --rebase`, `selective.record_pull(final, added,
modified, deleted)` with the lists from `diff_trees(final, orig_head)`, so `sgit checkout --since-pull` writes what
the rebase brought in.

### 5.8 Stops

At a stop the engine: materialises `tip` (5.7), writes what the stop needs, sets `stopped_reason`,
`stopped_item`, and the remaining `todo`, and exits 1.

#### 5.8.1 Conflict

- `materialize(tip)`, then write the merge result for `C`'s clean paths into the working copy (the paths in
  `merged_map` that differ from `T`) through the same writer, so the working copy is "tip + everything of C that
  applied".
- Whole-file conflicts: `write_conflict_files(directory, conflicts, theirs_map, …)` (`Vault__Merge.py:82-106`):
  the working file stays the tip's version (ours), `<path>.conflict` holds `C`'s version (theirs). Marker conflicts
  (`--merge lines`): `write_marker_files`.
- Merge state (design__01 fields): `operation = rebase`, `ours_commit_id = tip`, `theirs_commit_id = C`,
  `lca_id = P`, `source_commit_id = C`, `merge_style`, `conflict_style`, `marker_paths`, `conflict_paths`.
  This makes `sgit resolve` work unchanged and makes every existing `Vault__Merge__State.check_not_in_progress`
  caller refuse (pull, push), with the message adjusted for `operation == rebase` (5.15).

#### 5.8.2 Edit

`C` is replayed and committed normally (`new` created, `tip = new`), then `materialize(tip)` and stop. The user
may change files. `--continue` amends (5.9.1).

#### 5.8.3 Reword (non-interactive, no message)

`C` is replayed and committed with its original message, `materialize(tip)`, stop. `--continue -m MSG` re-creates
the tip commit with the same tree and parent and the new message (an amend of a commit that is not pushed, so no
check is needed beyond I1). Interactive mode never stops for a reword: the editor opens on `message` with the
original text, and runs `prepare-commit-msg`/`commit-msg` (5.13).

#### 5.8.4 Exec

`materialize(tip)`, then run the argv (5.10, `exec`). Exit 0: carry on. Non-zero: stop with `EXEC_FAILED`, record
the exit code; `--continue` carries on **without** re-running it (Git without `--reschedule-failed-exec`).

#### 5.8.5 Break, empty, missing blob

`break`: materialise and stop. `EMPTY`: 5.5.5. `MISSING_BLOB`: a sparse/selective clone needed a blob to merge and
the server could not be reached: stop with the blob ids listed; `--continue` retries the same item.

### 5.9 `--continue`, `--skip`, `--abort`, `--quit`

All four start with `Vault__Rebase__State.read` and `recover` (5.7).

#### 5.9.1 `--continue [-m MSG]`

| `stopped_reason` | Steps |
|---|---|
| `CONFLICT` | 1. `Vault__Merge.unresolved(...)`: any unresolved path → `Vault__Merge_Unresolved_Error` (design__01 §5.8), exit 1, nothing written. 2. Scan the working copy against `tip` exactly as `commit` does (`Vault__Sync__Commit.commit`, `:80-143`: `_scan_local_directory`, secret guard, scoped check), building the tree with `Vault__Sub_Tree.build(..., old_flat_entries, old_tree_ids)` so only changed folders are rebuilt. 3. If the tree equals `tip`'s: apply the empty policy (drop by default, Git's "nothing to commit" during a rebase becomes a skip). 4. Else create the commit with `C`'s message (or `-m MSG`), timestamp and signing as 5.5.6; `tip = new`; `materialized = new`; write the clone ref (reflog `rebase (continue): <subject>`). 5. Delete the merge state. 6. Carry on with the todo. |
| `EDIT` | If the working copy differs from `tip` (scan as above) or `-m` was given: re-create `tip` as an amend (same parent, new tree and/or message), `tip = amended`, record the rewrite, write the ref. Then carry on. |
| `REWORD` | `-m MSG` required, else refuse ("--continue needs -m MSG to reword <id>"). Re-create `tip` with the new message. Carry on. |
| `EXEC_FAILED`, `BREAK` | The working copy must be clean against `tip` (Git refuses to continue with uncommitted changes after an exec); else refuse naming the files. Carry on. |
| `EMPTY` | `--continue` drops it; `--continue --keep-empty` keeps it. |
| `MISSING_BLOB` | Retry the same item. |

#### 5.9.2 `--skip`

Allowed at `CONFLICT`, `EMPTY`, `MISSING_BLOB`, `REWORD` and `EDIT` (Git allows `--skip` at any stop). Steps:
remove this stop's conflict files (`Vault__Merge__Abort._remove_conflict_files`, path-guarded); `materialize(tip)`
with `materialized` treated as unknown on the touched paths (the paths of `C`'s change set are rewritten to `tip`'s
content even if the user edited them, as Git's `--skip` does); delete the merge state; record
`result = dropped`; carry on. At `EDIT`/`REWORD` the commit already created for the item is discarded:
`tip` = its parent.

#### 5.9.3 `--abort`

1. Remove conflict files of the current stop (if any).
2. `materialize(orig_head)` with `materialized` = the state's value. The working copy goes back on exactly the
   paths the rebase changed, plus the paths the user edited during a stop on those paths. **Files the user edited
   at a stop on other paths**: Git's `--abort` does `reset --hard` and discards them. sgit does the same but prints
   them first (`Discarding uncommitted changes: …`), because `reset` already behaves that way
   (`Vault__Sync__Pull.reset`, `:60-66`) and the user asked to abort. To scope the reset, a scan of the working copy
   against `materialized` lists the dirty paths, and those paths are added to the rewrite set.
3. Clone ref = `orig_head`, reflog reason `rebase (abort)`.
4. Delete merge state and rebase state.
5. Autostash: pop (5.12.4).

#### 5.9.4 `--quit`

Delete the rebase state and any `operation = rebase` merge state; leave the ref, the working copy and conflict files
as they are. The autostash is **kept** in the stash list and named in the output (Git keeps it too).

### 5.10 Todo actions, precisely

| Action | Effect on `tip` | Stops? | Commit message | Hooks (5.13) |
|---|---|---|---|---|
| `pick C` | replay C onto tip | on conflict / empty-stop | C's (`message_enc` reused) | `prepare-commit-msg <file> message`, `post-commit` |
| `reword C` | replay C | interactive: no (editor); `--todo` with `message`: no; `--todo` without: yes (`REWORD`) | new | `pre-commit`, `prepare-commit-msg <file> commit HEAD`, `commit-msg`, `post-commit`, `post-rewrite amend` |
| `edit C` | replay C, then stop | yes (`EDIT`) | C's (or `-m`) | pick's at replay; amend's at `--continue` if amended |
| `squash C` | replay C onto tip, then **fold** into the previous commit of the group: the group's single commit has parent `squash_base`, the latest tree, the messages joined (5.10.1) | interactive: editor on the joined message; non-interactive: joined text, or the item's `message` | joined | `prepare-commit-msg <file> message`, `commit-msg` (message edited), `post-commit` |
| `fixup C` (`use_message=previous`) | as squash | no | the group's first message | as pick |
| `fixup -C C` (`this`) / `-c` (`this-edit`) | as squash | `-c` opens the editor | C's | as pick / as squash |
| `drop C` | none | no | none | none |
| `exec ARGV` | none (materialises tip) | on non-zero exit | none | none |
| `break` | none (materialises tip) | yes (`BREAK`) | none | none |

**5.10.1 Squash groups.** A run of `squash`/`fixup` items after a `pick`/`reword`/`edit` forms a group. The
engine keeps `squash_base` (the parent of the group's first commit) and `squash_messages`. Each item is replayed
onto the current tip (which may be an intermediate group commit), then the group commit is re-created as
`parent = squash_base`, `tree = latest tree`, `message = combined`. Intermediate group commits are orphan objects
(never referenced; harmless; no GC needed since they are never pushed). Combined message, Git's layout without
comment lines: messages in order, separated by a blank line; fixups contribute nothing (`previous`) or replace the
whole text (`this`).

**5.10.2 `exec`.** Run with `subprocess.run(argv, cwd=<vault root>, env=Vault__Hooks().environment(directory,
None), stdin=DEVNULL, check=False)` (design__03 5.5: secrets stripped, `SGIT_DIR` etc. set; `GIT_*` removed). No
shell; `argv` comes from the JSON list or `shlex.split` of the text line. A user who wants a shell writes
`exec sh -c "make && make test"`. stdout/stderr inherited (under `--json`, stdout goes to stderr). No timeout unless
`SGIT_EXEC_TIMEOUT` (seconds) is set, matching design__03 D8.

### 5.11 Refs, reflog, `ORIG_HEAD`, undo

- `Vault__Ref_Manager.write_ref(ref_id, commit_id, read_key=None, reason: str = None, reflog_old: str = None)`
  (`Vault__Ref_Manager.py:16`): `reflog_old` overrides the recorded old value; `reason` is stored on the entry.
  Existing callers are unchanged (both default `None`).
- `Vault__Reflog.append(ref_id, old, new, reason=None)` (`Vault__Reflog.py:31`).
- Reasons written: `rebase (start): onto <O short>` (only when the first materialisation happens),
  `rebase (pick|continue|reword|edit): <subject>` at stops, `rebase (finish): onto <O short>` at the end (with
  `reflog_old = orig_head`), `rebase (abort)`.
- **Undo after a rebase.** `history undo` (`Vault__Sync__History_Edit.undo`, `:39-57`) uses the newest entry's
  `old_commit`. The finish entry's `old_commit` is `orig_head`, so one undo restores the pre-rebase head and files.
  Its pushed-head refusal does not fire: the rebased head is not on the server.
- **ORIG_HEAD.** Written at the start (`Vault__Storage.write_private`). `Vault__Revision._base` (`:83`) learns the
  name `ORIG_HEAD`; the rebase is its only writer in this design (Git also sets it on reset and merge: follow-up).
- `history reflog` prints the reason column when present.

### 5.12 `pull --rebase`

#### 5.12.1 Workflow

New `Workflow__Pull__Rebase` in `sgit_ai/workflow/pull/Workflow__Pull__Rebase.py`, registered like
`Workflow__Pull` (`Workflow__Pull.py:13`):

```
steps = [Step__Pull__Derive_Keys, Step__Pull__Load_Branch_Info, Step__Pull__Fetch_Remote_Ref,
         Step__Pull__Fetch_Missing, Step__Pull__Rebase]
```

The first four are **unchanged**: the rewind guard, the signature policy and verify-then-accept run exactly as for a
merge pull, and they are the only writers of the local named ref and the baseline (I3).

`Vault__Sync__Pull.pull(directory, on_progress=None, accept_rewind=False, merge_from=None, checkout=True,
rebase: bool = None, autostash: bool = None, merge_style=None, conflict_style=None)`
(`Vault__Sync__Pull.py:80`): `rebase is None` → the clone's `pull_rebase`. Before running the workflow it also
checks `Vault__Rebase__State.check_not_in_progress(directory, 'pull')`.

#### 5.12.2 `Step__Pull__Rebase`

`sgit_ai/workflow/pull/Step__Pull__Rebase.py`, same input/output schema as `Step__Pull__Merge`
(`Schema__Pull__State`):

| Case | Same test as the merge step | Action |
|---|---|---|
| no named head / equal | `Step__Pull__Merge.py:75-80` | `up_to_date` |
| clone head ancestor of named | `:99` (`lca == clone`) | fast-forward exactly as the merge step (the same code, moved into a shared helper `Pull__Fast_Forward`) |
| named ancestor of clone | `:96` | `up_to_date` (nothing to rebase onto) |
| diverged, no rewind | `:119` | `Vault__Sync__Rebase.start(directory, upstream=named, onto=named, from_pull=True, …)` |
| accepted rewind | `:87-95` | 5.12.3 |

The result maps onto `Schema__Pull__State.merge_status`: `rebased` (new value), `rebase_stopped` (new value), with
`merge_commit_id` = the final tip and `conflict_paths` at a stop. `_pull_state_to_dict` (`Vault__Sync__Pull.py:159`)
returns `status = 'rebased' | 'rebase_stopped'`; `CLI__Vault.cmd_pull` prints 3.5's text.

#### 5.12.3 Accepted rewind: the fork point

When `Fetch_Remote_Ref` accepted a rewind, `workspace.rewound_from` is the old named head the clone last accepted
(`Step__Pull__Fetch_Remote_Ref.py:52-55`). The clone's own commits are those reachable from `H` and not from
`rewound_from`; they go onto the new named head:

```
start(upstream = rewound_from, onto = named_commit_id, held_heads = {rewound_from, named_commit_id})
```

That is Git's `--fork-point` result, with the baseline standing in for the upstream's reflog. Differences from
today's `_take_rewind` (`Step__Pull__Merge.py:245-310`): commits are replayed one by one (history kept instead of
squashed), and a conflict stops for resolution instead of refusing. Merge pulls keep `_take_rewind` as it is.

#### 5.12.4 Autostash

`autostash = flag, else local_config.rebase_autostash`. Start: if the working copy is dirty
(`_require_clean`'s status), `Vault__Stash.stash` and record the zip name in `state.autostash`; print
`Created autostash: <name>`. Finish or abort: `Vault__Stash.pop`; on any pop failure the stash is kept and the output
says `Applying autostash failed; your changes are safe in the stash (sgit vault stash pop).` Without autostash, a
dirty working copy refuses: `cannot rebase: you have uncommitted changes (commit them, sgit vault stash them, or
pass --autostash)`.

#### 5.12.5 Push's implicit pull

`Vault__Sync__Push.push` pulls first (`Vault__Sync__Push.py:177-182`). It now passes `rebase=None` (the clone's
setting) and `autostash=False`. Results:

- `rebased` → push continues with the rebased head: a fast-forward.
- `rebase_stopped` → push raises: `the pull before the push stopped a rebase at <id> (conflicts in …); resolve and
  run sgit history rebase --continue, then push again` (today's message for merge conflicts is at `:180-182`).

Decision D4 asks whether the implicit pull should rebase when `pull_rebase` is on (recommended) or always merge.

### 5.13 Hooks (design__03's runner)

`Enum__Hook_Name` gains `PRE_REBASE` and `POST_REWRITE`. `VERIFY_HOOKS` gains `PRE_REBASE` (Git's `--no-verify`
covers it for rebase).

| When | Hook | Args / stdin | Failure |
|---|---|---|---|
| Before anything (after argument checks, before the state exists) | `pre-rebase` | `$1` upstream as the user typed it (or the named branch name), `$2` absent (sgit rebases the current clone only) | non-zero refuses the rebase, nothing written |
| First materialisation, and the final one | `post-checkout` | `<old> <new> 1` | ignored (warning), as design__03 |
| Each `pick`/`squash`/`fixup` commit | `prepare-commit-msg` (`<file> message`), `post-commit` | message file = `.sg_vault/local/rebase/message` | `prepare-commit-msg` non-zero stops the rebase (reason `CONFLICT`-free stop: `EXEC_FAILED` with the hook named) |
| A `reword` or `-c` fixup or interactive squash (message edited) | `pre-commit`, `prepare-commit-msg <file> commit HEAD`, `commit-msg`, `post-commit`, `post-rewrite amend` (`<old> <new>`) | as Git (measured) | `pre-commit` / `commit-msg` non-zero stops with the hook named; `--continue` retries |
| End (done, not aborted) | `post-rewrite` | `$1 = rebase`; stdin: one `<old> <new>` line per rewritten commit, full ids | ignored |
| `pull --rebase` | as above; **not** `post-merge` (Git's `pull --rebase` does not run it) | | |

Hooks are only run when design__03's `Vault__Hooks.find` finds one, so the cost without hooks is a stat per hook
name per rebase.

### 5.14 Signing

- Clone key: always, as every commit (`_load_signing_key`). A missing key prints the existing UNSIGNED warning
  (`Step__Pull__Merge.py:168-169`) once per rebase, not per commit.
- User key (design__02): `Signing__Config__Resolver.resolve(state.signing)` once at start; the resolved
  `User__Signer` signs every created commit (pick, reword, squash group, amend at `--continue`), as Git re-signs
  during a rebase when `commit.gpgsign` is on. If the signer fails (agent missing, key locked), the step stops with
  reason `EXEC_FAILED`-style message naming the signer, nothing created for that step; `--continue` retries.
- Original user signatures are **not** carried (the bytes differ; design__02 7.1 says the same of amend).

### 5.15 Other commands during a rebase

`Vault__Rebase__State.check_not_in_progress` is called at the start of:

| Command | Behaviour during a rebase | Where |
|---|---|---|
| `pull`, `push`, `branch merge` | refused | `Vault__Sync__Pull.pull` (`:88`), `Vault__Sync__Push.push` (`:50`) |
| `commit`, `commit --amend`, `write`, `write --push` | refused: "a rebase is in progress: use sgit history rebase --continue (it commits your resolution)" (decision D8) | `Vault__Sync__Commit.commit` (`:32`), `write_file` (`:231`) |
| `branch switch/new/checkout/rename`, `history reset/undo/revert --as-commit`, cherry-pick, `vault stash` / `stash pop`, `vault move/rekey/format`, `merge-abort` | refused (`merge-abort`: "use sgit history rebase --abort") | the respective entry points |
| `bisect start` | refused; and `history rebase` refuses during a bisect (`Vault__Bisect__State.check_not_in_progress`) | design__05 |
| `resolve` | allowed (works on the `operation = rebase` merge state) | unchanged |
| `status`, `history log/diff/show/reflog`, `fetch`, `checkout <paths>` (selective), `cat`, `ls` | allowed | — |
| `history rebase` (a new one) | refused: "a rebase is already in progress" | — |

`Vault__Merge__State.check_not_in_progress` (`Vault__Merge__State.py:42-49`) reads the state's `operation`; when it
is `rebase` the message becomes the rebase one, so the commands that already check merge state say the right thing.
**Commit with merge state `operation = rebase`** must not create a two-parent merge commit: `Vault__Sync__Commit`
refuses it (design__01 §5.8 step 4 lists the operations; `rebase` is added to the refusal branch).

A start-of-rebase check also refuses when a merge, cherry-pick or bisect is in progress.

### 5.16 File-by-file changes

| File | Change |
|---|---|
| `sgit_ai/core/actions/rebase/__init__.py` | new (source tree only) |
| `sgit_ai/core/actions/rebase/Vault__Sync__Rebase.py` | new: `start(...)`, `continue_(directory, message=None, keep_empty=False)`, `skip(directory)`, `abort(directory)`, `quit(directory)`, `show_todo(directory)`, `edit_todo(directory, todo_text=None)`, `_run(state)` (the todo loop), `_finish(state)` |
| `sgit_ai/core/actions/rebase/Vault__Rebase__State.py` | new (5.3) |
| `sgit_ai/core/actions/rebase/Vault__Rebase__Planner.py` | new (5.4) |
| `sgit_ai/core/actions/rebase/Vault__Rebase__Todo.py` | new: `parse_text(text, c) -> Schema__Rebase_Todo`, `parse_json(text, c)`, `render_text(todo, header)`, `autosquash(todo, subjects)`, `add_exec(todo, argvs)` |
| `sgit_ai/core/actions/rebase/Vault__Rebase__Replay.py` | new (5.5): `replay`, `_change_set`, `_sub_maps`, `_unify_equal_content`, `_df_conflicts` |
| `sgit_ai/core/actions/rebase/Vault__Rebase__Working_Copy.py` | new (5.7): `materialize`, `recover`, `dirty_paths` |
| `sgit_ai/core/actions/rebase/Vault__Rebase__Exec.py` | new (5.10.2) |
| `sgit_ai/core/actions/checkout/Vault__Working_Copy__Writer.py` | new: `_write_selective` + `_refuse_unwritten` moved out of `Step__Pull__Merge` (`:218-243`), which calls it |
| `sgit_ai/core/actions/history/Vault__Commit_Graph.py` | new or shared with design__05 (D9): `parents`, `generation`, `paint`, `range`, `merge_bases` |
| `sgit_ai/storage/Vault__Sub_Tree.py` | `apply_changes` (5.6), `entry_at` (5.5.2) |
| `sgit_ai/storage/Vault__Ref_Manager.py` | `write_ref(..., reason=None, reflog_old=None)` |
| `sgit_ai/storage/Vault__Reflog.py` | `append(..., reason=None)` |
| `sgit_ai/schemas/Schema__Reflog_Entry.py` | `reason` |
| `sgit_ai/schemas/Schema__Local_Config.py` | `pull_rebase`, `rebase_autostash` |
| `sgit_ai/schemas/rebase/*.py` | the schemas of 5.2 |
| `sgit_ai/safe_types/*.py` | the enums and Safe types of 5.2 |
| `sgit_ai/core/Vault__Errors.py` | `Vault__Rebase_Error`, `Vault__Rebase_In_Progress_Error` (both refusals, added to `_print_friendly_error`'s list at `CLI__Main.py:1210-1214`) |
| `sgit_ai/core/actions/history/Vault__Revision.py` | `ORIG_HEAD` |
| `sgit_ai/core/actions/merge/Vault__Merge__State.py` | rebase-aware message in `check_not_in_progress` |
| `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` | the two `check_not_in_progress` calls; refuse commit on `operation = rebase` merge state |
| `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` | `pull(..., rebase=None, autostash=None, …)`; rebase check |
| `sgit_ai/workflow/pull/Workflow__Pull__Rebase.py`, `Step__Pull__Rebase.py` | new (5.12) |
| `sgit_ai/workflow/pull/Step__Pull__Merge.py` | fast-forward block moved to `Pull__Fast_Forward` (shared); `_write_selective` calls the new writer |
| `sgit_ai/schemas/workflow/pull/Schema__Pull__State.py` | `merge_status` values `rebased`, `rebase_stopped` (`merge_status` is a plain `Safe_Str`, `Schema__Pull__State.py:48`, so no type change; update its comment), `rebase_steps : list[Schema__Rebase_Done_Item]` for output |
| `sgit_ai/core/actions/push/Vault__Sync__Push.py` | implicit pull passes `rebase=None`, handles `rebase_stopped`; **branch-only fix**: at `:664`, if `remote_head` is not an ancestor of `clone_commit_id` (`Vault__Ref_Guard.is_ancestor`), use the local named head as `stop_at`, so a rebased WIP branch uploads only the new chain and its CAS write replaces the old server clone ref |
| `sgit_ai/core/actions/status/Vault__Sync__Status.py` | `rebase_info` (3.7) |
| `sgit_ai/plugins/history/CLI__History.py` | the `rebase` subparser (3.2) dispatching to a new `CLI__Rebase` |
| `sgit_ai/cli/CLI__Rebase.py` | new: argument handling, editor launch, output (3.5), `--json` |
| `sgit_ai/plugins/history/plugin.json` | `"rebase"` in `commands` |
| `sgit_ai/cli/CLI__Main.py` | pull parser `--rebase/--no-rebase/--autostash` (`:398-406`); friendly errors |
| `sgit_ai/cli/CLI__Vault.py` | `cmd_pull` passes the flags and prints rebase results (`:963`); `cmd_status` prints 3.7; `cmd_reflog` prints the reason |
| `sgit_ai/core/hooks/*` (design__03) | `PRE_REBASE`, `POST_REWRITE` |

### 5.17 Compatibility

- **No format change, no gate.** Every replayed commit is an ordinary `commit_v1` object with one parent, a tree
  built by the same rules, a clone signature and (optionally) a design__02 user signature. Old clients and the web
  UI read, verify and pull it like any commit.
- **No server change.** I2: the rebase writes nothing remote; `pull --rebase` writes exactly what a merge pull
  writes; the following push is an ordinary fast-forward.
- **Local files.** New fields in `config.json`, `reflog.jsonl` and `merge_state.json` are optional; an older build
  ignores them (unknown keys accepted) and, if it rewrites `config.json`, drops `pull_rebase`, which falls back to
  merge: fail-safe.
- **An older build during a rebase stop** sees `merge_state.json` and refuses pull/push with the merge message; it
  does not know `operation = rebase` and would let `sgit commit` make a two-parent commit. Acceptable: mixing
  builds inside one working copy mid-rebase is not supported, and `sgit update` is the remedy (stated in the
  CHANGELOG entry).
- `Workflow__Pull` (merge) is unchanged byte for byte when rebase is off.

---

## 6. Security and threat model

| ID | Risk | Actor | Mitigation | Test |
|---|---|---|---|---|
| T1 | **A rebase rewrites pushed history**, so the next push (with `--force`) or pull makes every other clone see a rewind | A4 (self, by mistake) | I1: the todo excludes, and every edited todo re-checks, commits reachable from the local named ref and the accepted baseline; there is no override in v1 (D2) | `test_Security__Fixed__Rebase_Boundaries.test_pushed_commit_is_never_replayed` (named `Fixed` as it pins a refusal; see D10), plus a todo naming a pushed commit |
| T2 | **The baseline moves, so the rewind guard goes blind** | A1 + self | I3: the engine never calls `_write_remote_baseline` or writes the named ref; `pull --rebase` leaves those writes to the unchanged fetch steps | `test_Rebase__Refs.test_baselines_and_named_ref_untouched` (bytes of `remote_heads.json` and the named ref file compared before/after, including after abort) |
| T3 | **Laundering an unsigned or foreign commit** into this clone's signed history under `signatures-required` | A3 | Foreign commits refused without `--allow-foreign`; with it, they must verify under the vault's policy before re-signing (5.4.2) | `test_Rebase__Signing.test_unsigned_foreign_commit_refused_under_policy` |
| T4 | **Re-attribution** (a teammate's work signed as mine) | A4 | Same check; `post-rewrite` and `--json` list rewritten ids | `test_Rebase__Signing.test_foreign_commit_refused_by_default` |
| T5 | **`exec` runs commands** | user, agent (A9) | Only from the user's todo (`--exec`, `-i`, `--todo`), never from vault content: the state and todo live under `.sg_vault/local/`, which vault content cannot write (path guard refuses `.sg_vault` segments, TM-F03); argv, no shell; secrets stripped from the environment (design__03 5.5) | `test_Rebase__Exec.test_argv_not_shell` (an argument containing `; touch x` creates no `x`), `test_environment_has_no_secrets` |
| T6 | **Conflict labels from commit subjects** inject marker lines | A3 | design__01 `Safe_Str__Conflict_Label` (T2 there) | design__01's test, plus `test_Rebase__Conflicts.test_subject_with_markers_in_label` |
| T7 | **A tampered state file** points the abort or the replay elsewhere | local user | Same trust as `config.json` (local, 0600); ids are `Safe_Str__Commit_Id`; `orig_head`, `onto` and every todo commit must be local commits; I1 re-checked on load; `exec` argv only from the user's own todo | `test_Rebase__State.test_damaged_state_refuses_with_remedy` |
| T8 | **Plaintext on disk**: `message` and the text todo hold commit subjects | A6 | 0600, inside `.sg_vault/local/` like `COMMIT_EDITMSG` (design__03) and the flat cache (TM-R41); deleted at finish/abort/quit | `test_Rebase__State.test_files_are_private_and_removed` |
| T9 | **Hostile paths in replayed changes** (`../x`, `.sg_vault/...`) | A3 (a commit from another clone with `--allow-foreign`) | Every working-copy write goes through the existing writer and `Vault__Path_Guard.safe_join`; `apply_changes` takes names only from decrypted tree entries, which the tree reader already validates | reuse `test_Security__Fixed__Hostile_Paths` with a rebase variant |

**Threat-model rows to add** (`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`):

- **TM-R44 (accepted):** a rebase re-signs replayed commits with this clone's key; with `--allow-foreign` another
  clone's commit is re-attributed. Bounded by the foreign-commit refusal and by the signature policy check.
  Residual: a user who passes `--allow-foreign` can claim a teammate's change as theirs (they could equally copy the
  files and commit). Evidence: T3/T4 tests.
- **TM-R45 (accepted):** `exec` and `pre-rebase`/`post-rewrite` hooks run user-chosen programs with the user's
  rights; secrets are stripped from their environment but the programs can read `.sg_vault/local/` (same as
  design__03's hooks row).
- **Invariant note on TM-F12/F19 (baselines):** rebase is listed among the operations that never move a baseline.

---

## 7. Interactions

| With | Behaviour |
|---|---|
| **Full clone** | As designed. |
| **Scoped clone (`--path`)** | Flats are never built; `diff_trees` and `apply_changes` open only held spine folders; out-of-scope siblings are carried inside the loaded trees. A commit touching unheld folders is refused (5.4.2). `pull --rebase` on a scoped clone works like its merge pull. |
| **Shallow clone (`--depth`)** | The range walk stops at boundaries; refusal when the range cannot be proven (5.4.1 step 4). The unpushed range is always above the boundary in normal use. |
| **Sparse / selective working copy** | Materialisation writes only checked-out paths and records the rest; conflict merging may need upstream blobs not local: fetched verified on demand, else stop `MISSING_BLOB` (5.8.5). `record_pull` after `pull --rebase`. |
| **Read-only clone** | Refused before anything: `Vault__Read_Only_Error` (no clone branch, no signing key). |
| **Pack vaults** | Replayed commits and trees are local loose objects, exactly as `commit` creates them; the next push sends them as a commit pack and writes its index pack. The commit index's change list can serve 5.5.1. |
| **`--pack-store` clones** | Reads go through the pack store as today; new objects are written where `commit` writes them. |
| **Worktrees (design__06)** | Each worktree has its own `.sg_vault/local/` (state, ORIG_HEAD, reflog) and its own clone branch: independent rebases. New objects go to the worktree's own store per design__06; reads fall through to the main store. Two worktrees rebasing concurrently do not share refs. |
| **Bisect (design__05)** | Mutually exclusive (5.15). |
| **Hooks (design__03)** | 5.13. `--no-verify` skips `pre-rebase` only. |
| **Line merge (design__01)** | `--merge lines` gives marker conflicts and clean line merges inside the replay; default stays whole-file `.conflict` (the agreed default). |
| **Cherry-pick (design__01)** | Shares `Vault__Merge` wiring, `pick_message`, the writer and (follow-up) `apply_changes`. A cherry-pick in progress blocks a rebase and the reverse. |
| **Stash** | `--autostash` uses it; `vault stash` is refused during a rebase. |
| **Rewind re-apply** | Merge pulls keep `_take_rewind`; rebase pulls use the fork point (5.12.3). |
| **`history undo`** | One undo after a finished rebase returns to `orig_head` (5.11). |
| **`push --branch-only`** | A rebased WIP branch pushes cleanly after the `stop_at` fix (5.16). |
| **Web UI / other clients** | See only ordinary commits after the push. |

---

## 8. Performance

Measured costs from the 0.26.0 release-readiness note (76,000 files in 58,553 folders, in-memory host): full clone
61 s, push of a 5-file commit 4.5–5.2 s, `history log` of 4 commits 0.45 s. Estimates below are per step, from the
code paths each step uses; the acceptance list (9.4) requires measuring them.

| Step | Cost driver | Estimate on 76k files |
|---|---|---|
| Range walk | one commit decrypt per commit not yet in the generation memo; then O(range + upstream since base) | < 0.5 s for a 50-commit range; first run on a loose vault walks the history once (626 commits ≈ 1 s) |
| Cherry detection | `diff_trees` per upstream commit since the merge base (only differing folders) | ~10–30 ms per commit; capped at 2,000 commits |
| Replay of one commit changing `k` files at depth `d` | `diff_trees` (≈ `k·d` folder loads) + `entry_at` for `k` paths (cached spine) + `apply_changes` (≈ `k·d` folder rebuilds) + one commit create/sign | ~20–100 ms for `k` ≤ 10 |
| Materialisation | `diff_trees(target, materialized)` + writing the changed files | proportional to files changed by the whole rebase; one write per file per rebase (not per step) |
| `pull --rebase` | the merge pull's fetch cost (unchanged) + the above | dominated by the fetch, as a merge pull is |

**What is avoided.** `build_from_flat` re-encrypts all 58,553 folders per call (4); a replay that used it would
cost tens of seconds per commit on this vault. `apply_changes` rebuilds only the spines. No step builds a full flat
map; the only full scan is the clean-tree check at start (the scan cache makes it a stat per file: 6.5 s on the
228,000-file vault, CHANGELOG 0.26.0) and the scan at `--continue`.

**Caps.** `REBASE_CHERRY_SCAN_MAX = 2000`; the line engine's caps are design__01 D8's. A todo longer than
`REBASE_TODO_WARN = 500` items prints a warning (no refusal).

---

## 9. Test plan

All unit tests use real objects: two clones over `Vault__API__In_Memory` via `Vault__Test_Env` (fixed test key),
no mocks. No `__init__.py` in tests. File and class names follow the repository convention.

### 9.1 Planner and todo — `tests/unit/core/actions/rebase/`

`test_Vault__Rebase__Planner.py` → `Test_Vault__Rebase__Planner`:

1. Linear: 3 local commits, 2 upstream → todo is the 3, oldest first.
2. Merge commits in the range are dropped; both sides linearised in topological order (the measured Git case:
   `mer1, side1, after`).
3. A local commit equal in effect to an upstream commit (same path, same old and new content hash, different blob
   ids) is `skipped_upstream`; with `reapply_cherry_picks` it is in the todo.
4. Range when the local named ref and the baseline differ (both excluded).
5. Explicit upstream `HEAD~2` that would include a pushed commit → refused (I1), naming it.
6. `--onto X`: replays `U..H` on X.
7. `--keep-base`: onto = merge base; several merge bases → refused.
8. Up to date; fast-forward case.
9. Shallow clone: range above boundary works; range crossing a boundary refused with the `--unshallow` hint.
10. Foreign commit refused; `--allow-foreign` admits it; under `signatures-required` an unsigned foreign commit is
    refused even with the flag.
11. Scoped clone: a commit touching an unheld folder refused.
12. The generation walk agrees with a brute-force reachability on 200 random DAGs (property test; the oracle is
    a set computed by full ancestor walks).

`test_Vault__Rebase__Todo.py` → `Test_Vault__Rebase__Todo`: text parse (every verb, short forms, prefixes, comments,
blank lines, unknown verb refused with line number, ambiguous prefix refused); JSON parse (array and object forms,
`argv` vs `command`, `use_message`); render then parse round trip; autosquash ordering (`fixup!`, `squash!`, nested,
no target → left in place); `--exec` insertion after squash groups; Type_Safe round trip of every schema
(`from_json(obj.json()).json() == obj.json()`).

### 9.2 Replay and trees

`tests/unit/storage/test_Vault__Sub_Tree__Apply_Changes.py` → `Test_Vault__Sub_Tree__Apply_Changes`:

- I6 property test: 300 random trees (depth ≤ 6, up to 400 files), random change maps (add, modify, delete, delete
  the last file of a folder, add into a new nested folder, file↔folder swaps) → `apply_changes(T, Δ)` equals
  `build_from_flat(flatten(T) ⊕ Δ)`, id for id.
- A scoped clone's tree with carried siblings: ids equal the full builder's.
- Cost: on a 20,000-file synthetic tree, changing one file loads ≤ depth+1 trees (counted with an instrumented
  `Vault__Object_Store` subclass that counts loads — a real subclass, not a mock).

`tests/unit/core/actions/rebase/test_Vault__Rebase__Replay.py` → `Test_Vault__Rebase__Replay`: clean replay;
replay onto a tip that changed other files; equal-content-different-blob normalisation (5.5.3) is not a conflict;
modify/delete and delete/modify conflicts; folder/file collisions both ways; empty after replay with each `--empty`
policy; message bytes reused (same `message_enc`); timestamp kept / `--reset-date`; signature verifies with the
clone key and `author_key_id` set.

### 9.3 End to end — `tests/unit/core/actions/rebase/test_Vault__Sync__Rebase.py` and `tests/unit/workflow/pull/test_Pull__Rebase.py`

| Class | Cases |
|---|---|
| `Test_Vault__Sync__Rebase__Basic` | the common agent case: clone A pushes, clone B commits twice and rebases onto the new named head; B's push is a fast-forward (`push` uploads only the new chain); a third clone pulls with no rewind warning |
| `Test_Vault__Sync__Rebase__Conflicts` | stop on conflict (files style): working file = tip version, `.conflict` = commit version, merge state `operation=rebase`; `resolve --theirs` + `--continue` → commit with the original message; `--continue` with unresolved → refused, nothing written; lines style: markers, clean line merge, unresolved check; `--skip` drops the commit and restores the touched paths; `--abort` restores ref, files, deletes state |
| `Test_Vault__Sync__Rebase__Interactive` | every verb via `--todo` JSON and text; reword with and without message; edit then amend at `--continue` (with and without file changes, with `-m`); squash and fixup groups incl. `-C`; drop; break; exec success and failure (`exec` writes a marker file through argv to prove it ran in the vault root with tip's files present); `--edit-todo` re-checks I1; `-i` with `SGIT_SEQUENCE_EDITOR` set to a small Python script that rewrites the file (a real program, no mock) |
| `Test_Vault__Sync__Rebase__Recovery` | crash simulation without mocks: run the engine with a `Vault__Rebase__Working_Copy` subclass that raises after writing N files (a real subclass overriding one method); then `--continue` converges (I5) and `--abort` restores (I4); damaged `state.json` refuses with the remedy; `--quit` leaves everything |
| `Test_Vault__Sync__Rebase__Refs` | reflog reasons; finish entry's `old_commit == orig_head`; one `history undo` restores; `ORIG_HEAD` resolves; I3 byte comparison of `remote_heads.json` and the named ref file |
| `Test_Vault__Sync__Rebase__Guards` | every refused command of 5.15 during a stop, each with nothing written; rebase refused during merge, cherry-pick, bisect, dirty tree (and `--autostash` path incl. failed pop keeping the stash) |
| `Test_Vault__Sync__Rebase__Partial_Clones` | scoped, shallow, selective (`--no-checkout`: only checked-out paths written, `checkout --since-pull` writes the rest after `pull --rebase`), read-only refused, pack vault (push after rebase sends one commit pack; `pack index verify` passes) |
| `Test_Pull__Rebase` | diverged pull rebases; FF and up-to-date unchanged; conflict stop → `status = rebase_stopped`; `pull_rebase = on` default and `--no-rebase` override; push's implicit pull rebases and refuses on a stop; accepted rewind replays own commits individually onto the new head (compare with today's squashed `_take_rewind`) |
| `Test_Push__Branch_Only_After_Rebase` | WIP pushed with `--branch-only`, rebased, pushed again: only the new chain uploaded, server clone ref replaced, no error |

**Git as the oracle.** `tests/unit/core/actions/rebase/test_Rebase__Git_Oracle.py` → `Test_Rebase__Git_Oracle`
builds the same history in a temporary Git repository (git 2.43 is installed; the test is skipped with a reason if
`git` is absent) and in sgit, runs both rebases, and compares: the list of replayed subjects in order, the skipped
ones, the final file contents per path, and which commit stops on conflict. Histories: the measured cases of 1.2
plus 50 generated ones (random linear and merge-bearing local ranges over a shared base). File contents are
compared exactly for clean replays; conflict stops are compared by commit and path set (marker bytes are design__01's
concern).

### 9.4 Security tests — `tests/security/`

`test_Security__Fixed__Rebase_Boundaries.py` → `Test_Security__Fixed__Rebase_Boundaries`: a todo (text and JSON)
naming a pushed commit; an explicit upstream reaching below the baseline; a planted `exec` in a file committed to
the vault under `.sg_vault/local/rebase/todo` (refused by the path guard at commit; never read by the engine);
`exec` argument with shell metacharacters; hostile path in a foreign commit with `--allow-foreign`; I3 bytes check
after a stop, a continue and an abort.

### 9.5 CLI — `tests/unit/cli/test_CLI__Rebase.py`

Parser (every flag, mutual exclusions `--onto`/`--keep-base`, `--continue` with other options refused), exit codes
(0/1 per 3.6), `--json` shape keys, help text present, `history` plugin lists `rebase`, `TOP_LEVEL_COMMANDS`
unchanged (`test_CLI__B07__Namespace_Moves.py` passes untouched).

### 9.6 Acceptance checklist (implementation and deployment)

Implementation:

- [ ] `pytest tests/unit/ -n auto` green; `pytest tests/security` green; new tests from 9.1–9.5 present and passing.
- [ ] I6 property test passes with 300 random trees; `apply_changes` used by the replay (no `build_from_flat` on
      the replay path; checked by a load-count assertion).
- [ ] Git oracle test passes on the 50 generated histories.
- [ ] I1, I3, I4, I5 each have a named test (9.3/9.4) and pass.
- [ ] Every refusal in 5.4.2 and 5.15 writes nothing (state, ref, working copy compared before/after).
- [ ] Type_Safe round trip for every new schema.
- [ ] `TOP_LEVEL_COMMANDS` unchanged; `history` plugin lists `rebase`.
- [ ] CHANGELOG entry under `[Unreleased]` (Added: rebase, pull --rebase; Changed: reflog reasons; Fixed:
      branch-only push after a rewritten WIP chain); threat-model rows TM-R44, TM-R45; README "Rebase" section.

Deployment (on the dev pre-release, then the release):

- [ ] On the 76,000-file synthetic vault (in-memory host): rebase of 10 one-file commits onto a head 5 commits
      ahead completes in ≤ 5 s, and the working copy is written once (count of file writes = files changed);
      measured numbers recorded in the release note.
- [ ] Same rebase on a pack vault; the following push sends one commit pack and `pack index verify --last 1`
      passes.
- [ ] Two real clones on the dev server (`--transport api`): `pull --rebase` with a conflict, resolve,
      `--continue`, push; a third clone pulls with no rewind warning and `check verify` shows every commit verified.
- [ ] `history undo` after the rebase restores the pre-rebase head; `push` after undo behaves as before the rebase.
- [ ] An interrupted rebase (process killed mid-materialisation on the real vault) recovers with `--continue` and
      with `--abort`, both checked with `status` clean and `check fsck` clean.
- [ ] A web-UI read of the vault after the push shows the rebased commits (no format surprise).

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `feat(storage): apply_changes and entry_at — rebuild only the changed spines` | 5.6, 5.5.2; I6 property tests; load-count test | 0.5 day |
| 2 | `refactor(history): shared commit graph (generations, painting, range, merge bases)` | `Vault__Commit_Graph` (or the shared part of design__05's graph, D9); brute-force property tests | 0.5 day |
| 3 | `feat(rebase): state, todo parse/render, planner` | 5.2, 5.3, 5.4; planner and todo tests; `--dry-run` CLI | 1 day |
| 4 | `feat(rebase): replay loop, lazy working copy, finish, abort, quit` | 5.5, 5.7, 5.9.3–5.9.4, 5.11 (reflog reason, ORIG_HEAD); basic end-to-end tests; recovery tests | 1 day |
| 5 | `feat(rebase): conflicts, --continue, --skip, guards in other commands` | 5.8.1, 5.9.1–5.9.2, 5.15; needs design__01's merge state fields and `unresolved` (or lands with them) | 1 day |
| 6 | `feat(rebase): interactive todo — reword, edit, squash, fixup, drop, exec, break, autosquash` | 5.10, 5.8.2–5.8.5, editor launch | 1 day |
| 7 | `feat(pull): pull --rebase, pull_rebase, autostash; push's implicit pull; branch-only fix` | 5.12, 5.16 push changes | 0.5–1 day |
| 8 | `feat(rebase): hooks and user signing` | 5.13, 5.14 (after design__02/03 land; otherwise a no-op seam) | 0.5 day |
| 9 | `test(rebase): Git oracle, security tests, 76k measurement; docs` | 9.3 oracle, 9.4, CHANGELOG, threat model, README, release-note numbers | 0.5–1 day |

**Total: 6.5–7.5 days** for one developer, after design__01's merge-state and classifier changes (rebase step 5
depends on them; steps 1–4 do not). The roadmap's earlier "2–3 days" assumed whole-file merges only, no
interactive mode and no pull integration.

---

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | A top-level `sgit rebase` alias | (a) only `history rebase` + `pull --rebase`; (b) also top-level `rebase` (a `TOP_LEVEL_COMMANDS` edit) | **(a)**. Rule 9 puts commit rewriting under `history`; the daily case is `pull --rebase` |
| D2 | Rewriting pushed commits | (a) never in v1; (b) `--rewrite-pushed` with a warning, needing `push --force` and `pull --accept-rewind` on every other clone | **(a)**. The deliberate path already exists (`history reset` + `push --force`), and keeping rebase local-only is what makes it safe for agents |
| D3 | Commits signed by another clone in the range | (a) refuse unless `--allow-foreign`; (b) replay and re-sign silently (Git keeps the author; sgit cannot) | **(a)**. Signing is attribution in sgit; silent re-attribution would be a surprise |
| D4 | Push's implicit pull when `pull_rebase = on` | (a) rebase (consistent with `pull`); (b) always merge | **(a)**, refusing the push if the rebase stops |
| D5 | Default for `pull_rebase` | (a) off (merge, today); (b) on | **(a)**: the agreed principle is opt-in; teams can turn it on per clone |
| D6 | `exec` lines | (a) argv (shlex), `sh -c` explicitly when wanted; (b) through the shell as Git does | **(a)**, the TM-F06 lesson: no implicit shell |
| D7 | Timestamps of replayed commits | (a) keep the original (Git's author date); (b) now (Git's committer date) | **(a)** with `--reset-date`; `log` keeps showing when the work was done |
| D8 | Work at an `edit`/conflict stop | (a) v1: `--continue` commits or amends, `sgit commit` refused; (b) allow `sgit commit` / `--amend` at stops and several commits per `edit` (Git) | **(a)** now; (b) as a follow-up (+1 day, needs commit to target the rebase tip) |
| D9 | Shared commit-graph class | (a) `Vault__Commit_Graph` used by bisect and rebase; (b) each keeps its own walk | **(a)**: one painting walk, one set of property tests |
| D10 | Security test naming | `test_Security__Fixed__Rebase_Boundaries` (pins refusals, like `Fixed__Baselines`) or a new `test_Security__Invariant__*` family | **`Fixed__`**: CLAUDE.md names only `Fixed` and `Known_Gaps`; these pin refusals that must hold |
| X1 | Cross-doc: equal content with different blob ids | (a) rebase normalises locally (5.5.3); (b) design__01's `three_way_merge` compares `content_hash` first for every caller | **(b)**, with (a) as the fallback if design__01 lands first without it. Pull merges, cherry-pick and revert have the same false conflict today |
