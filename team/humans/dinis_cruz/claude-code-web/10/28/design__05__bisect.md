# Design 05: `sgit history bisect` (roadmap item 2.6)

**Status:** design, not started. **Roadmap:** `roadmap__git-parity.md`, priority 2, item 2.6.
**Code read for this document:** this repository at `3a1d72a` (`claude/charming-babbage-5hzcxq`).
**Git used as the reference:** git 2.43.0 (installed here). Every Git behaviour quoted below was either run here
against a scratch repository or read from `builtin/bisect.c` / `bisect.c`; the run-here ones are marked *(run)*.

---

## 1. Summary, and the exact Git behaviour matched

`sgit history bisect` finds the commit that introduced a change by binary search over the commit graph, like
`git bisect`. The user (or a command, with `run`) marks commits good or bad; sgit writes each candidate commit
into the working copy until one commit is left.

The one structural difference from Git is where "HEAD" is. Git detaches HEAD and leaves the branch alone. sgit
has no separate HEAD: the clone branch's ref *is* the head. So bisect **never moves any ref**. It records the
commit under test in a local state file and writes that commit's files into the working copy; status, cat, ls
and checkout read that commit while a bisect is in progress. `reset` writes the clone head's files back. Because
no ref moves, a lost or damaged state file can never lose a commit: the head was never touched.

### Git behaviour matched

| Behaviour | Git 2.43 | sgit |
|---|---|---|
| Start | `git bisect start [<bad> [<good>...]] [--] [<pathspec>...]`, with `--term-old/--term-new`, `--first-parent`, `--no-checkout` | same, under `sgit history bisect` |
| Marks | `bad`/`new`, `good`/`old` (with no rev: the commit under test), `skip [<rev>|<range>...]` | same |
| One bad, many goods | a later `bad` replaces the earlier one; goods accumulate | same |
| Candidate set | ancestors(bad) minus ancestors(each good), bad included, goods excluded | same (5.3) |
| Midpoint | weight(c) = number of candidates reachable from c, c included; choose the commit maximising `min(w, n − w)`; Git returns early on the first commit whose weight is within half, in its counting order | same score; ties broken by the smaller weight, then generation, then id (5.4). Equal to Git on linear histories and on the vectors in 9.3 *(run)* |
| Skip | if the best candidate is skipped, Git sorts candidates by distance and picks with `skip_away`: `prn = ((count·1103515245 + 12345) mod 2³²) / 65536 mod 32768`, `index = (count·prn / 32768) · isqrt(prn) / isqrt(32768)` | ported exactly (5.5) |
| Progress line | `Bisecting: <n> revisions left to test after this (roughly <s> steps)` with `n = all − weight − 1`, `s = estimate(all)` *(run)* | same text, sgit ids |
| Step estimate | `all < 3 → 0`; else `k = floor(log2 all)`, `e = 2^k`, `x = all − e`, `k if e < 3x else k − 1` *(run: 15→3, 8→2, 4→1, 2→0)* | same |
| Done | `<id> is the first bad commit`, then the commit as `git show --stat` prints it *(run)* | `<id> is the first bad commit`, then `history show <id>` |
| Only skipped left | `There are only 'skip'ped commits left to test. The first bad commit could be any of: <ids> We cannot bisect more!`; `run` exits 2 *(run)* | same; `run` exits 2 |
| Good not an ancestor of bad | tests the merge base first: `Bisecting: a merge base must be tested`; a bad merge base stops with `The merge base <mb> is bad. This means the bug has been fixed between <mb> and [<goods>].` | same |
| `run <cmd>` exit codes | 0 good; 125 skip; 1–127 except 125 bad; < 0 (signal) or ≥ 128 abort, state kept, `run` exits with that code *(run: 128 → exit 128)* | same |
| 126/127 on the first run | Git re-runs the command on a good commit; the same code there means the command itself is broken: `bogus exit code <n> for good revision`, exit 1 *(run)*. Otherwise it is "bad" | same |
| `run` echo | `running '<argv>'` before each run *(run)* | `running <argv>` |
| State | `.git/BISECT_START` (original branch), `BISECT_TERMS`, `BISECT_LOG`, `BISECT_NAMES` (pathspec), `BISECT_FIRST_PARENT`, `BISECT_HEAD` (no-checkout), `refs/bisect/bad`, `refs/bisect/good-<sha>`, `refs/bisect/skip-<sha>` *(run)* | one file, `.sg_vault/local/bisect.json` (5.1); per clone, never synced |
| `log` / `replay` | `BISECT_LOG` is `# bad: [...]` comments plus `git bisect …` lines *(run)*; `replay <file>` re-applies them | same format with `sgit history bisect …` lines; replay also accepts `git bisect …` lines |
| `visualize` / `view` | `gitk` or `git log` over the remaining candidates | `history log` over the remaining candidates |
| `reset [<commit>]` | back to the original branch, or to `<commit>` | back to the clone head; `reset <commit>` = `reset` then `history reset <commit>` (5.7) |
| `terms` | prints the terms | same |
| `next` | re-computes and checks out the next candidate | same |

---

## 2. Scope and non-goals

**In scope:** `start`, `bad`/`new`, `good`/`old`, custom terms, `skip` (single revs and `A..B` ranges), `next`,
`reset`, `log`, `replay`, `view`/`visualize`, `run`, `terms`, `status` (sgit extra: the state as text or JSON),
`--first-parent`, `--no-checkout`, a pathspec, `--json` on every subcommand. Full, selective (sparse /
no-checkout), scoped, shallow, read-only, pack and pack-store clones. The commands that must refuse or change
behaviour while a bisect is in progress (7.1).

**Not in scope:**
- `gitk`. `view` prints a log; nothing graphical.
- Moving refs. Bisect never writes a ref, a baseline, the branch index or the reflog.
- Network writes of any kind (6.3 proves it).
- Fetching history behind a shallow boundary on its own. A shallow clone says so and stops (7.3).
- Committing during a bisect. Git allows commits on its detached HEAD, which `bisect reset` then orphans; sgit
  refuses them (decision D1).
- Changing `branch checkout <commit>`'s existing "detached" behaviour (`CLI__Vault.py:1567`, which writes every
  file of the commit with no state and no dirty check). It is a related hazard noted in 11 (D7), not fixed here.

---

## 3. CLI surface

Rule 9: bisect is about commits, so it goes under `history`. No top-level command is added.

### 3.1 Subcommands

| Command | Arguments and flags | Does |
|---|---|---|
| `sgit history bisect start` | `[<bad> [<good>...]] [--term-old T] [--term-new T] [--term-good T] [--term-bad T] [--first-parent] [--no-checkout] [-- <path>...]` | records the state; if a bad and at least one good are known, checks out the first candidate |
| `sgit history bisect bad` / `new` / `<term-new>` | `[<rev>...]` (Git takes one for bad; extras refused) | marks bad (default: the commit under test) |
| `sgit history bisect good` / `old` / `<term-old>` | `[<rev>...]` | marks each good (default: the commit under test) |
| `sgit history bisect skip` | `[<rev> | <A>..<B>]...` | marks skipped (default: the commit under test) |
| `sgit history bisect next` | | re-computes and checks out the next candidate |
| `sgit history bisect reset` | `[<commit>] [--force]` | ends the bisect, writes the clone head back (5.7) |
| `sgit history bisect log` | | prints the replayable log |
| `sgit history bisect replay` | `<file>` | resets, then re-applies a log |
| `sgit history bisect view` / `visualize` | `[--oneline] [-n N]` | `history log` of the remaining candidates |
| `sgit history bisect run` | `[--shell] [--timeout SECONDS] -- <cmd> [<arg>...]` | loops: run, mark, next (5.8) |
| `sgit history bisect terms` | `[--term-good | --term-bad]` | prints the terms |
| `sgit history bisect status` | | sgit extra: state, current commit, counts, the next step |

Every subcommand takes `--directory DIR` (default `.`) and `--json`.

**Custom terms.** Git accepts `git bisect fixed` after `--term-new fixed`. argparse cannot add sub-parsers at run
time, so `bisect` is one parser with `subcommand` (positional) and `args` (`argparse.REMAINDER`), and
`CLI__Bisect.dispatch` maps the word: a built-in subcommand, `good/bad/old/new`, or the recorded term names.
A term may not be a subcommand name (`help start skip next reset visualize view replay log run terms status`),
and old and new may not be equal: Git's rule, enforced by `Safe_Str__Bisect_Term` plus a check in `start`
(decision D2).

### 3.2 Output (text)

```
$ sgit history bisect start HEAD HEAD~15
Bisecting: 7 revisions left to test after this (roughly 3 steps)
[a1b2c3d4e5f6] c8 — the commit message's first line
  wrote 1 file, removed 0 (working copy is now at a1b2c3d4e5f6; your branch head is unchanged)

$ sgit history bisect good
Bisecting: 3 revisions left to test after this (roughly 2 steps)
[…] c12

$ sgit history bisect bad
…
obj-cas-imm-9f8e7d6c5b4a is the first bad commit
<history show output for it>
  (sgit history bisect reset   returns the working copy to your branch head)
```

Waiting states, as Git words them: `status: waiting for both good and bad commits`, `status: waiting for good
commit(s), bad commit known`, `status: waiting for bad commit, 1 good commit known`.

`status` during a bisect gains a first line: `Bisecting: working copy at <id> (<k> candidates left); branch head
<id> unchanged. sgit history bisect reset to return.`

### 3.3 Exit codes

| Situation | Exit |
|---|---|
| any mark, `start`, `next`, `skip`, `view`, `log`, `terms`, `status`, `reset` that succeeded (including "first bad commit found") | 0 |
| a refusal (bad revision, dirty files in the way, a bisect not in progress, a merge in progress, bad term) | 1 |
| `run`: first bad commit found | 0 |
| `run`: only skipped commits left | 2 |
| `run`: the command exited < 0 or ≥ 128 | that code (a signal: 128 + signal number, as a shell reports it) |
| `run`: bogus 126/127 (same code on a good commit) | 1 |
| `run`: the merge base is bad | 1 |

### 3.4 `--json` shape

Every subcommand prints one JSON object (`run` prints one at the end; with `--json` it prints no per-step text):

```json
{
  "status":      "bisecting",           // waiting | bisecting | found | only_skipped | merge_base_bad | reset
  "terms":       {"old": "good", "new": "bad"},
  "bad":         "obj-cas-imm-…",       // null while unknown
  "good":        ["obj-cas-imm-…"],
  "skipped":     [],
  "current":     "obj-cas-imm-…",       // the commit in the working copy; null with --no-checkout until marked
  "remaining":   7,                     // Git's "revisions left to test after this"
  "steps":       3,                     // Git's "roughly N steps"
  "candidates":  15,                    // size of the candidate set
  "first_bad":   null,                  // the id when status = found
  "possible":    [],                    // the ids when status = only_skipped
  "branch_head": "obj-cas-imm-…",       // never changes during a bisect
  "written":     1, "deleted": 0, "kept_dirty": [], "not_written": [],
  "paths":       [],                    // the pathspec
  "first_parent": false, "no_checkout": false
}
```

`run --json` adds `"runs": [{"commit": "…", "exit_code": 0, "verdict": "good", "seconds": 0.4}]`.

---

## 4. How the code works today (file:line)

| Piece | Where | What matters for bisect |
|---|---|---|
| Revision syntax | `core/actions/history/Vault__Revision.py:25-165` | `resolve()` (`:27`) turns HEAD, `~n`, `^n`, `@{n}`, tags, short ids into a commit id, **local only**; `_parent()` (`:159`) already says "history stops before … (shallow clone?)" |
| Commit graph walks | `core/actions/fetch/Vault__Fetch.py:78` `find_lca` | returns one LCA and caps each ancestor walk at `limit=200`: not usable for bisect (needs all merge bases, unbounded) |
| | `core/Vault__Sync__Base.py:767` `_walk_commit_ids` | BFS, `limit=200`: same problem |
| | `core/actions/pull/Vault__Ref_Guard.py:23` `is_ancestor` | local walk capped at `LOCAL_WALK_LIMIT = 100000` (`:17`): reusable for single checks |
| | `storage/graph/Vault__Graph_Walk.py:4` | tree walks only, not commits |
| Generation numbers | `core/actions/pack/Vault__Pack_Index.py:137` `generation_of` | `1 + max(parent generations)`, a non-local parent counts 0, memoised in `.sg_vault/local/index/generations.json` (`:70`, `:115-135`). It only needs the object store, so it works on loose vaults too |
| Tree diff | `storage/Vault__Sub_Tree.py:259` `diff_trees` | walks only folders whose ids differ: the cost of a step follows the change |
| Flatten + cache | `storage/Vault__Sub_Tree.py:133` `flatten`, `:186` `_flatten_incremental`, `:11-14` | in-process cache of 4 trees, on-disk cache of the newest 2 heads (`flat-cache/<tree id>.json`) |
| Scoped flatten | `storage/Vault__Scoped_Tree.py:39` `flatten(tree, key, scope) -> (flat, opaque)` | in-scope files only |
| Scope / shallow | `storage/Vault__Scope.py:65` `from_local_config`, `:74` `is_scoped`, `:77` `is_shallow`, `:83` `is_boundary` | boundaries are the commits whose parents were never fetched |
| Writing files | `core/Vault__Sync__Base.py:674` `_checkout_flat_map` | writes, seeds the scan cache, reports failures per path |
| Deleting files | `core/Vault__Sync__Base.py:738` `_remove_deleted_flat` | guarded by `Vault__Path_Guard.is_writable` |
| Dirty guard | `core/actions/pull/Vault__Pull__Guard.py:30` `dirty_paths`, `:59` `plan`, `:101` `blocked_targets`, `:127` `message`; used by `workflow/pull/Step__Pull__Merge.py:327` `_guard_working_tree` | carries dirty files a move does not touch; refuses before writing when it would overwrite one |
| Selective working copy | `workflow/pull/Pull__Selective.py:13` (`split` `:37`, `after_write` `:59`); `storage/Vault__Checkout_Set.py:151` `materialised` | which changed paths a selective clone writes |
| Selective checkout | `core/actions/checkout/Vault__Sync__Checkout.py:35` `checkout`, `:150` `_changed_since` | `--changed-since` diffs a commit **against the clone head**: the right tool between head and a commit, not between two bisect steps (5.6 uses `diff_trees` directly) |
| Head flat for cat / ls / checkout | `core/actions/sparse/Vault__Sync__Sparse.py:12` `_get_head_flat_map`, `:87` `sparse_ls`, `:177` `sparse_cat`, `:248` `_local_head_commit` | where the "working commit" hook goes (5.9) |
| Status | `core/actions/status/Vault__Sync__Status.py:16`; head flat at `:57-67`; read-only path `:339` | compares the disk with the clone head's flat |
| Current "detached" checkout | `cli/CLI__Vault.py:1519` `cmd_checkout`; `core/actions/revert/Vault__Revert.py:43` `revert_to_commit` | writes **every** file of the commit, decrypting every blob, no dirty check, no state; `status` and `commit` then see a revert. Bisect must not reuse it |
| History reset | `core/actions/pull/Vault__Sync__Pull.py:24` `reset` | moves the clone ref and writes the full flat |
| Reflog | `storage/Vault__Reflog.py:24`; every `Vault__Ref_Manager.write_ref` appends | bisect writes no ref, so nothing reaches it |
| Merge state pattern | `core/actions/merge/Vault__Merge__State.py:9` (`MERGE_STATE_FILE`), `:42` `check_not_in_progress`; called by pull (`Vault__Sync__Pull.py:88`), push (`Vault__Sync__Push.py:50`) | the model for `Vault__Bisect__State` |
| Stash | `core/actions/stash/Vault__Stash.py:27` `stash` (reverts to the clone head), `:76` `pop` | would overwrite the bisect working copy |
| History CLI | `plugins/history/CLI__History.py:70` `register`; plugin wiring `plugins/history/Plugin__History.py:9`; legacy `cli/CLI__Main.py:1285` | where `bisect` is registered |
| Friendly errors | `cli/CLI__Main.py:1196` `_print_friendly_error` (the tuple at `:1203-1213`) | new errors are added there |
| Subprocess pattern | `core/serve/Container__Command_Runner.py:15` | argv list, no shell, `FileNotFoundError` → 127, timeout → 124 |
| In-memory host | `network/api/Vault__API__In_Memory.py:8` (`_store` `:11`) | snapshot for the "nothing written" test |

---

## 5. Design

### 5.1 State: `.sg_vault/local/bisect.json`

Written with `Vault__Secret_File.write` (`crypto/Vault__Secret_File.py:14`: temp file 0600, rename). It holds
commit ids and paths, which `.sg_vault/local/` already holds (reflog, flat cache), so 0600 is consistency, not
secrecy.

New types:

| File | Class | Definition |
|---|---|---|
| `sgit_ai/safe_types/Safe_Str__Bisect_Term.py` | `Safe_Str__Bisect_Term(Safe_Str)` | `regex = re.compile(r'^[a-z][a-z0-9_-]{0,31}$')`, `regex_mode = MATCH`, `max_length = 32`, `allow_empty = False`, `strict_validation = True` |
| `sgit_ai/safe_types/Enum__Bisect_Verdict.py` | `Enum__Bisect_Verdict(Enum)` | `GOOD = 'good'`, `BAD = 'bad'`, `SKIP = 'skip'` (the internal meaning; terms are display) |
| `sgit_ai/safe_types/Enum__Bisect_Status.py` | `Enum__Bisect_Status(Enum)` | `WAITING`, `BISECTING`, `FOUND`, `ONLY_SKIPPED`, `MERGE_BASE_BAD` |
| `sgit_ai/safe_types/Enum__Bisect_Log_Action.py` | `Enum__Bisect_Log_Action(Enum)` | `START`, `GOOD`, `BAD`, `SKIP`, `FOUND` |

Schemas (folder `sgit_ai/schemas/bisect/`, like `schemas/merge/`):

```python
class Schema__Bisect_Log_Entry(Type_Safe):
    action    : Enum__Bisect_Log_Action  = None
    commit_id : Safe_Str__Commit_Id      = None
    args      : list[Safe_Str__Commit_Id]          # START: [bad, good...]; SKIP of a range: every id
    subject   : Safe_Str__Commit_Message = None    # first line, for the "# bad: [...] subject" comment

class Schema__Bisect_Transition(Type_Safe):         # a step in flight (crash recovery, 5.6.4)
    from_commit : Safe_Str__Commit_Id = None
    to_commit   : Safe_Str__Commit_Id = None

class Schema__Bisect_State(Type_Safe):
    schema_version  : Safe_UInt                      # 1
    branch_id       : Safe_Str__Branch_Id   = None   # the clone branch when the bisect started
    branch_head     : Safe_Str__Commit_Id   = None   # its head then; checked on every command (7.1)
    term_old        : Safe_Str__Bisect_Term = None   # 'good' unless --term-old
    term_new        : Safe_Str__Bisect_Term = None   # 'bad'  unless --term-new
    bad             : Safe_Str__Commit_Id   = None
    good            : list[Safe_Str__Commit_Id]
    skipped         : list[Safe_Str__Commit_Id]
    current         : Safe_Str__Commit_Id   = None   # the commit whose files the working copy holds
    paths           : list[Safe_Str__File_Path]       # the pathspec ([] = everything)
    first_parent    : bool                  = False
    no_checkout     : bool                  = False
    merge_bases_ok  : bool                  = False   # Git's BISECT_ANCESTORS_OK
    transition      : Schema__Bisect_Transition = None
    first_bad       : Safe_Str__Commit_Id   = None
    started_ms      : Safe_UInt__Timestamp
    log             : list[Schema__Bisect_Log_Entry]
```

`Safe_Str__Commit_Message` exists (`safe_types/Safe_Str__Commit_Message.py`); the subject is its first line.

Round-trip invariant (CLAUDE.md rule 6): `Schema__Bisect_State.from_json(s.json()).json() == s.json()`.

### 5.2 Classes and responsibilities

All new code under `sgit_ai/core/actions/bisect/` (with an empty `__init__.py`, as every action package has).

| Class | Base | Responsibility |
|---|---|---|
| `Vault__Bisect__State` | `Type_Safe` | `path(directory)`, `exists`, `read` (a damaged file raises `Vault__Bisect_Error` naming the file and the remedy `bisect reset`), `write`, `delete`, `check_not_in_progress(directory, action)` (mirrors `Vault__Merge__State.check_not_in_progress`), `working_commit(directory) -> str` ('' when no bisect) |
| `Vault__Bisect__Graph` | `Type_Safe` | the commit graph and the choice: `parents(cid)`, `generation(cid)`, `candidates(state) -> list`, `weights(cands) -> dict`, `best(cands, weights, skipped) -> str`, `skip_away(sorted_cands, count)`, `prn(count)`, `isqrt(n)`, `estimate_steps(all)`, `merge_bases(a, b) -> list`, `touches_paths(cid, paths) -> bool` |
| `Vault__Bisect__Working_Copy` | `Vault__Sync__Base` | moves the working copy from one commit to another (5.6); `move(directory, from_id, to_id, state) -> dict(written, deleted, kept_dirty, not_written)` |
| `Vault__Bisect__Runner` | `Type_Safe` | runs the user's command (5.8): `run(argv, cwd, env, timeout, shell) -> Schema__Bisect_Run` |
| `Vault__Bisect__Log` | `Type_Safe` | `render(state) -> str`, `parse(text) -> list[Schema__Bisect_Log_Entry]` (parsing only; never executes) |
| `Vault__Sync__Bisect` | `Vault__Sync__Base` | the commands: `start`, `mark(verdict, revs)`, `skip(specs)`, `next`, `reset(commit=None, force=False)`, `log`, `replay(file)`, `view(n)`, `run(argv, ...)`, `terms`, `status` |
| `CLI__Bisect` | `Type_Safe` (`sgit_ai/cli/CLI__Bisect.py`) | argparse registration, `dispatch(args)`, text and JSON rendering |

Plus `Schema__Bisect_Run(Type_Safe)`: `exit_code : Safe_Int`, `seconds : Safe_Float`, `timed_out : bool`,
`verdict : Enum__Bisect_Verdict = None`, `aborted : bool`.

Errors (`sgit_ai/core/Vault__Errors.py`): `Vault__Bisect_Error(Exception)` for refusals by bisect itself and
`Vault__Bisect_In_Progress_Error(Exception)` for other commands refused during a bisect. Both are added to the
"refused on purpose" tuple in `CLI__Main._print_friendly_error` (`cli/CLI__Main.py:1203-1213`), so the user sees
`error: <message>` and no traceback.

### 5.3 The candidate set

Input: `bad`, `goods` (≥ 1), `skipped`, `paths`, `first_parent`.

1. **Painting walk** (`Vault__Bisect__Graph.candidates`). A max-heap of `(generation, commit_id)` starts with bad
   (flag NEW) and every good (flag OLD). Pop the highest generation; merge flags if seen; push its parents (only
   the first with `first_parent`) carrying the flag. Stop when every entry left in the heap is OLD (the
   `paint_down_to_common` rule: nothing below can be NEW-only). Candidates = commits painted NEW and not OLD.
   Generations come from `Vault__Pack_Index.generation_of` (`Vault__Pack_Index.py:137`), memoised in
   `local/index/generations.json`. On a loose vault the memo is built on first use (one decrypt per commit,
   once per clone). A commit not in the store (a shallow boundary's parent) has generation 0 and no parents.
   Unbounded: no `limit=200` (unlike `find_lca`, `Vault__Fetch.py:78`).
2. **Pathspec** (when `paths` is non-empty, or by default on a scoped clone, 7.3). A candidate is kept when
   `touches_paths` is true:
   - for each path, resolve the entry id (tree id or blob id) at that path in the commit's root tree and in each
     parent's, walking only the spine (one tree read per path segment, `Vault__Sub_Tree._entries_by_name`, `Vault__Sub_Tree.py:306`);
   - a non-merge commit touches when any id differs from its parent's;
   - a merge touches when, for some path, its id differs from **every** parent's (the merge itself changed it).
   Commits not kept stay in the graph for reachability (weights count only kept commits reachable through them).
   This approximates Git's history simplification, which also prunes merge parents; it is equal to Git on linear
   histories (tested, 9.3) and documented as an approximation for merges (decision D4).
3. **Skipped** commits stay candidates for counting (as in Git) and are excluded only when choosing.
4. **Ancestry check before the first step** (`merge_bases_ok` false): for each good g, if `is_ancestor(g, bad)`
   is false (`Vault__Ref_Guard.is_ancestor`, `:23`), compute `merge_bases(g, bad)` (all of them, by painting).
   - A merge base not yet marked: it is the next commit to test, with the line `Bisecting: a merge base must be
     tested`.
   - A merge base marked bad: stop with `Enum__Bisect_Status.MERGE_BASE_BAD` and Git's message, plus a hint:
     `if you are looking for the commit that FIXED something: sgit history bisect start --term-old broken
     --term-new fixed`.
   - A merge base marked skipped: print Git's warning (`… we cannot be sure the first bad commit is between <mb>
     and <bad>. We continue anyway.`) and continue.
   - All good: set `merge_bases_ok = True`, then continue normally.

### 5.4 The midpoint

`n = len(candidates)`. For each candidate c, `w(c)` = number of candidates reachable from c through the graph
(c included). Computation: process candidates in increasing generation; `reach(c) = {c} ∪ ⋃ reach(p)` over
parents restricted to the candidate subgraph. A bitset per commit (Python `int` used as a bitset, candidates
indexed 0..n−1) keeps this exact for DAGs at `n · n / 8` bytes: 10,000 candidates is 12.5 MB, acceptable. For
`n > 50,000`, use Git's approach: exact counts for single-parent chains (`w = w(parent) + 1`) and a bitset only
below merges. Linear histories are always `O(n)`.

Choice (`best`):
- `score(c) = min(w(c), n − w(c))`;
- skip commits in `skipped`;
- choose the highest score; ties go to the **smaller** `w`, then the lower generation, then the smaller id.

That tie rule reproduces Git on every vector run here (9.3): 15 linear → `c8` (w = 7, not `c9` with w = 8);
first-parent 5 → `m3`; the merge graph → `b3`. Git's own tie order depends on its counting order and, under skip,
on SHA-1 order, so for DAGs with ties the tests assert this documented rule, not Git's pick.

Progress numbers: `remaining = n − w(chosen) − 1`, `steps = estimate_steps(n)`; for 15 → `7`, `3`.

Termination:
- `n == 1` (only bad left): `first_bad = bad`, status `FOUND`.
- Every candidate but bad is skipped: status `ONLY_SKIPPED`, `possible` = skipped candidates plus bad, sorted by
  generation descending (Git prints them that way).
- Shallow clone and `first_bad` is a boundary commit (`Vault__Scope.is_boundary`): print
  `<id> is the first bad commit this clone can see: its parents are behind the shallow boundary (sgit fetch
  --unshallow, then sgit history bisect replay <log>)`; status `FOUND`, `"at_boundary": true` in JSON.

### 5.5 Skip (`skip_away`, ported from Git)

When the best candidate is skipped:
1. Sort the non-skipped candidates by `score` descending, ties by `w` ascending, then id (Git sorts by distance
   then oid).
2. `count = len(sorted)`, `prn = ((count * 1103515245 + 12345) & 0xFFFFFFFF) // 65536 % 32768`,
   `index = (count * prn // 32768) * isqrt(prn) // isqrt(32768)`.
3. Choose `sorted[index]`; if that is bad, choose the entry before it, or `sorted[0]`.

Vectors (`count → index`): 14 → 0, 13 → 6, 12 → 0, 7 → 3, 6 → 0 (computed with this formula; with Git on the
16-commit history, skipping c8 gave c9 (index 0) *(run)*).

`skip A..B` marks every commit in `ancestors(B) − ancestors(A)`, as Git does.

### 5.6 Moving the working copy between steps

`Vault__Bisect__Working_Copy.move(directory, from_id, to_id, state)`:

1. **Diff.** `diff_trees(tree(to), tree(from))` (`Vault__Sub_Tree.py:259`): only differing folders are opened.
   On a scoped clone, flatten both with `Vault__Scoped_Tree.flatten` (in-scope only) and diff the two maps.
   Result: `writes` (added and modified in `to`), `deletes` (in `from`, not in `to`).
2. **Guard (before any write).** The pull guard, with "ours" = `flat(from)` and "merged" = `flat(to)`:
   - `scan = _scan_local_directory(directory, verify=touched)`;
   - `dirty = Vault__Pull__Guard().dirty_paths(directory, ours, scan, obj_store=…, sparse=…, checkout=…)`;
   - `plan = guard.plan(dirty, ours, merged, scan, blob_hash_fn=…)`;
   - `blocked = plan['blocked'] + guard.blocked_targets(directory, writes, deletes)`.
   - A blocked path refuses the step with `Vault__Dirty_Working_Tree_Error(guard.message(blocked))`, nothing
     written: Git's "Your local changes to the following files would be overwritten by checkout".
   - Dirty files the move does not touch are carried over (Git behaves the same).
   Flattening `from` and `to` in full is avoided: the guard only needs the entries for `touched` paths, which the
   diff already returned, plus `scan`.
3. **Selective clones.** `Pull__Selective().setup(directory, obj_store, local_config, no_checkout=False)`;
   `to_write, skipped = selective.split(writes)`. Paths not checked out stay not checked out and are reported as
   `not_written`. After writing, `selective.after_write(written, deletes, stale=selective.stale_of(skipped, ours))`
   keeps the checkout record right (`Pull__Selective.py:59`).
4. **Missing blobs** (a loose sparse clone): batch-read through `api.batch_read`, verified before they are saved,
   exactly as `Vault__Sync__Checkout._download` (`Vault__Sync__Checkout.py:160`). This is a read; see 6.3.
5. **Write.** `_remove_deleted_flat` for deletes, then `_checkout_flat_map(directory, to_write, …, failed=failed)`
   (`Vault__Sync__Base.py:674`), which also seeds the scan cache. Any `failed` entry raises after the state
   records `current = to_id` (the files that were written are `to`'s), with the paths and reasons; `status`
   shows them as modified, and `next` or `reset` retries.

#### 5.6.1 Write order and crash recovery

1. Write the state with `transition = {from, to}`.
2. Apply the move.
3. Write the state with `current = to`, `transition = None`.

If a process dies between 1 and 3, the next bisect command sees `transition` and re-applies the move from `from`
to `to`. Files already written equal `to`'s versions, and the guard's plan treats bytes equal to the incoming
version as current (`Vault__Pull__Guard.plan`), so the retry writes only what is left. `reset` does the same
before returning to the head.

#### 5.6.2 `--no-checkout`

Like Git's `--no-checkout` (which keeps `BISECT_HEAD` instead of moving HEAD): nothing is written; `current`
moves and is shown. The run command gets `SGIT_BISECT_COMMIT` (5.8). During the bisect, `sgit cat <path>` and
`sgit ls` read the commit under test (5.9), so a script can do `sgit cat src/app.py | …` with no checkout. This is
the agent-friendly mode and the cheapest on a 76,000-file vault.

### 5.7 `reset`

1. If a `transition` is recorded, finish it (5.6.1).
2. Move the working copy from `current` back to the clone head (5.6), with the same guard: dirty files that the
   move would overwrite refuse the reset, naming them (`--force` overwrites, as `git bisect reset` does not
   need; we keep the guard by default because sgit has no index to protect them). Not touching the head's
   other files means a bisect on a 76,000-file vault resets in the time of its last diff.
3. Delete `bisect.json`.
4. `reset <commit>` (Git: "go to this commit instead of the original branch"): after 1–3, `Vault__Sync__Pull.reset
   (directory, commit)` (`Vault__Sync__Pull.py:24`), the existing `history reset`, which moves the clone ref and
   writes the reflog. That is the only path in this design that moves a ref, and it is an explicit user request.
5. If `bisect.json` is unreadable, `current` is unknown, and reset cannot tell the user's edits from files the
   bisect wrote. It compares the disk with the clone head's flat (`_scan_local_directory` against
   `flatten(head)`), refuses, and lists the paths that differ; `--force` writes the head's version of each.
   Commits are never at risk: no ref moved.

If the clone head moved during the bisect (it cannot through sgit, 7.1, but a second process or a manual ref edit
could), `reset` still returns to the *current* head and says `your branch head moved during the bisect (from X
to Y)`.

### 5.8 `run`

Loop:

```
if status is WAITING:      refuse: "bisect run needs a good and a bad commit first"
first = True
while status == BISECTING:
    r = Runner.run(argv, cwd=directory, env=env(current), timeout, shell)
    if r.aborted (exit < 0 or >= 128, or timeout):   print Git's message; exit with that code (state kept)
    code = r.exit_code
    if first and code in (126, 127):
        # Git's check: is the command itself broken? run it once on a good commit
        move working copy to good[0]; r2 = run(...); move back to current
        if r2.exit_code == code: error "bogus exit code {code} for good revision"; exit 1
    first = False
    verdict = GOOD if code == 0 else SKIP if code == 125 else BAD
    mark(verdict, [current])                         # prints the next "Bisecting: …" or the result
return 0 if FOUND, 2 if ONLY_SKIPPED, 1 if MERGE_BASE_BAD
```

`Vault__Bisect__Runner.run`:
- **argv, never a shell string.** `subprocess.run([str(a) for a in argv], cwd=directory, env=env,
  timeout=timeout, stdin=subprocess.DEVNULL)`, output passed through to the terminal (not captured), as Git does.
  A missing binary is 127 (the `Container__Command_Runner` rule, `:21`).
- **`--shell`** (sgit extra, explicit): `['/bin/sh', '-c', ' '.join(argv)]` on POSIX, `['cmd', '/c', …]` on
  Windows. Git always runs through the shell; sgit makes the shell opt-in so a path or a vault file name in the
  arguments is never interpreted (decision D3).
- **env:** a copy of `os.environ` plus `SGIT_BISECT_COMMIT=<current>`, `SGIT_BISECT_BAD=<bad>`,
  `SGIT_BISECT_STEP=<n>`, `SGIT_BISECT_TERM_OLD`, `SGIT_BISECT_TERM_NEW`. Never the vault key, read key, write key
  or token: those are not added, and the variables sgit itself reads for secrets are not set by bisect.
- **cwd:** the vault directory (the working copy root), as Git runs in the worktree.
- **timeout** (sgit extra): `--timeout SECONDS`; a timeout kills the process group and counts as an abort (exit
  124 printed, `run` exits 124). Decision D5 offers "count it as skip" instead.
- **Ctrl-C:** `KeyboardInterrupt` stops the loop, state kept, exit 130.
- Each run prints `running <argv joined with shlex.join>`.

### 5.9 The "working commit" hook (what other commands read during a bisect)

One method, `Vault__Bisect__State.working_commit(directory) -> str`, returns `current` during a bisect and ''
otherwise. Three places use it:

| Place | Today | During a bisect |
|---|---|---|
| `Vault__Sync__Status.status` (`status/Vault__Sync__Status.py:57-67`, read-only `:339`) | flat of the clone head | flat of `working_commit`; adds `bisecting`, `bisect_current`, `bisect_candidates`, `bisect_branch_head` to the result; ahead/behind still use the clone head |
| `Vault__Sync__Sparse._get_head_flat_map` (`sparse/Vault__Sync__Sparse.py:12`), used by `cat`, `ls`, `checkout <paths>` | the clone head | `working_commit` |
| `Vault__Sync__History_Edit._require_clean` (`history/Vault__Sync__History_Edit.py:116`) | status | unchanged (status already answers against the working commit) |

`history log`, `history diff` and `history show` keep reading the clone head and explicit revisions; `view` is the
bisect-specific log. (Git's `git log` during a bisect starts from the detached HEAD. sgit users get the same
through `history log <current>`; decision D6.)

### 5.10 File-by-file changes

New files:

| File | Contents |
|---|---|
| `sgit_ai/safe_types/Safe_Str__Bisect_Term.py` | 5.1 |
| `sgit_ai/safe_types/Enum__Bisect_Verdict.py`, `Enum__Bisect_Status.py`, `Enum__Bisect_Log_Action.py` | 5.1 |
| `sgit_ai/schemas/bisect/__init__.py`, `Schema__Bisect_State.py`, `Schema__Bisect_Log_Entry.py`, `Schema__Bisect_Transition.py`, `Schema__Bisect_Run.py` | 5.1, 5.2 |
| `sgit_ai/core/actions/bisect/__init__.py`, `Vault__Bisect__State.py`, `Vault__Bisect__Graph.py`, `Vault__Bisect__Working_Copy.py`, `Vault__Bisect__Runner.py`, `Vault__Bisect__Log.py`, `Vault__Sync__Bisect.py` | 5.2–5.8 |
| `sgit_ai/cli/CLI__Bisect.py` | 3, rendering |

Changed files:

| File | Change |
|---|---|
| `sgit_ai/plugins/history/CLI__History.py` | field `bisect : object = None`; in `register` (`:70`), `bisect_p = hist_sub.add_parser('bisect', …)` with `subcommand`, `args` (REMAINDER), `--directory`, `--json`; `set_defaults(func=self.bisect.dispatch)`; module docstring lists bisect |
| `sgit_ai/plugins/history/Plugin__History.py` | `ns.bisect = context.get('bisect') or CLI__Bisect()` |
| `sgit_ai/cli/CLI__Main.py` | builds `CLI__Bisect` with the vault/diff CLIs and passes it in the plugin context; `_cmd_log_dispatch` (`:1285`) unchanged; the error tuple (`:1203-1213`) gains both bisect errors |
| `sgit_ai/core/Vault__Errors.py` | `Vault__Bisect_Error`, `Vault__Bisect_In_Progress_Error` |
| `sgit_ai/core/actions/status/Vault__Sync__Status.py` | 5.9 |
| `sgit_ai/cli/CLI__Vault.py` `cmd_status` (`:826`) | prints the bisect line first |
| `sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py` `_get_head_flat_map` (`:12`) | 5.9 |
| `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` `commit` (`:32`), `write_file` (`:231`) | `Vault__Bisect__State().check_not_in_progress(directory, 'commit' / 'write')` first |
| `sgit_ai/core/actions/push/Vault__Sync__Push.py` (`:50`) | the same check beside the merge one |
| `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` `pull` (`:88`), `reset` (`:24`) | the same check (bisect's own `reset <commit>` calls `reset` after deleting the state) |
| `sgit_ai/core/actions/branch/Vault__Branch_Switch.py` `switch` (`:30`), `branch_new` (`:167`) | the same check |
| `sgit_ai/core/actions/stash/Vault__Stash.py` `stash` (`:27`), `pop` (`:76`) | the same check |
| `sgit_ai/core/actions/history/Vault__Sync__History_Edit.py` `undo` (`:39`), `revert_commit` (`:60`) | the same check |
| `sgit_ai/core/actions/revert/Vault__Revert.py` `revert_to_commit` / `revert_to_head` (`:27`, `:43`) | the same check (`branch checkout <commit>` and `history revert` without `--as-commit`) |
| `sgit_ai/core/actions/merge/Vault__Merge__State.py` | none; `Vault__Sync__Bisect.start` calls `check_not_in_progress(directory, 'bisect')` |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py` `create` (`:92`) | during a bisect, a create with no commit refuses: `say which commit (the working copy is at <current>, your branch head is <head>)` |

The `check_not_in_progress` message: `Cannot <action>: a bisect is in progress (working copy at <current>; your
branch head <head> is unchanged). sgit history bisect reset ends it.`

### 5.11 Compatibility

- **No format change, no gate.** Nothing is written to the vault or the host. Old clients, the web UI and other
  clones see nothing.
- An older sgit run inside a folder with a bisect in progress does not know `bisect.json`: its `status` would
  show the bisect commit's files as modifications and its `commit` would commit them. The guard against that is
  the user's, as with any local tool mix; `sgit update` is the remedy. Noted in the CHANGELOG entry.
- The `local/index/generations.json` memo is created on loose vaults too. It is a derived cache that
  `Vault__Pack_Index` already treats as such.

---

## 6. Security and threat model

### 6.1 Running user commands (`run`)

| Risk | Treatment |
|---|---|
| Shell interpretation of arguments (paths, vault file names) | argv list, no shell, unless `--shell` is given explicitly (5.8) |
| The command runs code from an old commit | inherent, as in Git: `run` executes whatever the commit under test contains. The help text says so: "run executes the code in each commit it tests; run it only on vaults you trust" |
| Planted files on `sys.path` / `PATH` (TM-F06: `pip.py` in the folder ran as the user) | cwd is the working copy by design (the test needs it). sgit itself never runs Python from there: bisect's own code runs in the sgit process, and the runner does not invoke `python`. The help text recommends `python -I` for Python test commands |
| Secrets in the child's environment | bisect adds only the `SGIT_BISECT_*` ids; no key, token or base URL is added. The user's existing environment is passed as Git passes it |
| Output injection into sgit's own parsing | none: sgit reads only the exit code |
| Long-running or hung commands | `--timeout`; Ctrl-C keeps the state |

### 6.2 State tampering

`bisect.json` is local. Whoever can write it can already write the working copy and the refs. What a damaged or
edited state can and cannot do:
- It cannot move a ref, push or delete a commit: bisect has no code path that writes a ref (except `reset
  <commit>`, an explicit user request through the existing `history reset`).
- Ids in it are re-validated on read (`Safe_Str__Commit_Id`) and must exist in the store; an unknown id refuses
  with `bisect state names a commit this clone does not have: sgit history bisect reset`.
- Paths in it (`paths`) are used only for matching, never joined to the disk path without
  `Vault__Path_Guard.safe_join`.
- A replay log (`replay <file>`) is untrusted text. `Vault__Bisect__Log.parse` accepts only lines matching
  `^(sgit history bisect|git bisect) (start|good|bad|old|new|skip|terms|<term>)( .*)?$` and `#` comments; every id
  is resolved through `Vault__Revision.resolve` (local only). Nothing in the file is executed; `run` lines are
  refused with a message.

### 6.3 No network writes during a bisect (proof)

- **By construction.** The only network calls in the bisect code are `api.batch_read` and `api.read_large`, for
  blobs a loose sparse clone lacks (5.6, step 4). `Vault__Sync__Bisect` gets `api` only to pass it to that
  download. No code path in `core/actions/bisect/` calls `write`, `batch` (the write batch), `delete`,
  `presigned_*`, the branch index writer, `Vault__Ref_Manager.write_ref`, push or pull. A unit test greps the
  package's source for those names (`test_Bisect__No_Write_Calls`), so a later change that adds one fails.
- **By test.** `test_Bisect__Nothing_Leaves_The_Clone` runs a full `run` bisect over a two-clone setup on
  `Vault__API__In_Memory` and asserts:
  - `api._store` (`Vault__API__In_Memory.py:11`) is byte-identical before and after;
  - the clone's ref files, `remote_heads.json`, the local branch index file and `reflog.jsonl` are
    byte-identical;
  - the other clone's `pull` afterwards reports nothing new.

### 6.4 Threat-model rows

- New accepted row (`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`): **TM-R4x — `history bisect
  run` executes code from historical commits in the working copy**, actor A5 (a vault containing hostile files)
  and user error, L/M, accepted as in Git, mitigations 6.1, evidence `test_Bisect__Runner`.
- New fixed-by-design note in the coverage map: bisect never writes refs or the host, evidence 6.3.

---

## 7. Interactions

### 7.1 Other commands during a bisect

| Command | Git during a bisect | sgit |
|---|---|---|
| `status` | works (HEAD detached) | works, against the commit under test, with the bisect line |
| `commit`, `commit --amend`, `write` | allowed on the detached HEAD; `bisect reset` orphans those commits | **refused** (D1) |
| `push` | allowed (pushes branches, not HEAD) | **refused**: sgit's push runs an implicit pull that writes the working copy |
| `pull`, `branch merge` | `git pull` fails on a detached HEAD | refused |
| `fetch <path>` (writes files) | n/a | refused |
| `fetch --unshallow` | allowed | allowed: it adds commits only; the candidate set is recomputed on the next command |
| `checkout <paths>`, `cat`, `ls` | read HEAD (the bisect commit) | read the commit under test (5.9) |
| `branch switch / new / checkout`, `history reset / undo / revert` (all forms) | allowed, and confuse the bisect | refused |
| `vault stash` / `stash pop` | allowed | refused: stash reverts to the clone head (`Vault__Stash.py:28`) |
| `history log / diff / show / reflog`, `check *`, `vault tag list/show` | allowed | allowed |
| `vault tag create` with no commit | tags HEAD = the bisect commit | refused, names both candidates (5.10) |
| A merge in progress | `git bisect start` refuses | `start` refuses (`Vault__Merge__State.check_not_in_progress`) |

### 7.2 Head moved under the bisect

Every bisect command compares the clone head with `state.branch_head`. If they differ (another process, a manual
edit), it continues and warns once: `your branch head moved during the bisect (from X to Y); the bisect is
unaffected and reset returns to Y`.

### 7.3 Clone shapes

| Clone | Behaviour |
|---|---|
| Full | as designed |
| Selective (`--sparse`, `--no-checkout`) | each step writes only the changed paths that are checked out (5.6.3); `not_written` lists the rest. With nothing checked out, `start` warns `no files are checked out: the test will see nothing (sgit checkout <paths> first, or use --no-checkout and sgit cat)` |
| Scoped (`--path`) | the pathspec defaults to the scope, so only commits that change a held folder are candidates, and the working copy holds only those folders. A user pathspec outside the scope refuses (`Vault__Scope.paths_outside`, `:122`) |
| Shallow (`--depth`) | a good below the boundary cannot be resolved (Vault__Revision already says "shallow clone? sgit fetch --unshallow"). Boundary commits are roots. A first bad commit at the boundary is reported as such (5.4) |
| Read-only | allowed: bisect writes no ref and nothing to the host; status's read-only path gets the same hook (5.9) |
| Pack vault | every object is local after the clone (packs are extracted on arrival), so no step downloads. Generations may come from the index packs' commit graph members instead of decrypting commits (optimisation, step 6 in 10) |
| Pack-store (`--pack-store`) | objects are read in place by offset through `Vault__Object_Store`; nothing changes |
| Worktree (design 06) | `bisect.json` lives in the worktree's own `.sg_vault/local/`, so each worktree has its own bisect, as Git keeps `BISECT_*` per worktree. The recommended agent pattern: `sgit worktree add ../bisect-wt` then bisect there, leaving the main working copy alone |
| Stash | refused during a bisect (7.1); a stash made before survives untouched |

---

## 8. Performance

- **Steps:** `⌈log2(n)⌉` for n candidates; 1,000 commits → about 10 steps.
- **Candidate set:** one walk per command over commits between bad and the goods, with generations memoised in
  `generations.json`. Decrypting a commit is about 0.1–0.3 ms; 10,000 commits ≈ 1–3 s once, then the memo makes
  it near-instant. Weights: linear `O(n)`; DAG bitsets `O(n²/8)` bytes (12.5 MB at 10,000), done in ms in Python
  integer ops.
- **A step's working-copy cost follows the change between two commits, not the vault.** `diff_trees` opens only
  differing folders; the guard verifies only touched paths (`_scan_local_directory(verify=touched)`); only changed
  files are written. On the 76,000-file vault (58,553 folders), a step between commits that differ by 300 files
  costs about what a 300-file pull's write costs (the pull of a 300-file pass measured 16.9 s in total, most of
  it fetch and flatten that a bisect step does not do). The first step from the head can be large (half the
  history's changes); later steps halve.
- **Status during a bisect** flattens the commit under test once; `_flatten_incremental` (`Vault__Sub_Tree.py:186`)
  derives it from a cached neighbour. The on-disk flat cache keeps two heads (`FLAT_CACHE_ON_DISK = 2`), so a long
  bisect evicts the head's entry; after reset the head is re-derived incrementally. Acceptable; no change.
- **`--no-checkout`** writes nothing: a step is the graph work plus whatever the test reads with `sgit cat`.
- Measure on the 76,000-file synthetic vault before release: `start` + 10 marks with and without
  `--no-checkout`, recorded in the CHANGELOG.

---

## 9. Test plan

All tests are real objects over `Vault__API__In_Memory` with `Vault__Test_Env` (fixed `TEST_VAULT_KEY`); no mocks,
no `__init__.py` in test folders. Git is the oracle where the result is defined by Git (9.3); `git` is
installed in CI's unit image (check, else mark those tests to skip when `shutil.which('git')` is empty, with a
clear reason).

### 9.1 Files and classes

| File | Class | Covers |
|---|---|---|
| `tests/unit/schemas/bisect/test_Schema__Bisect_State.py` | `Test_Schema__Bisect_State` | round trip, defaults, bad ids rejected, list fields |
| `tests/unit/safe_types/test_Safe_Str__Bisect_Term.py` | `Test_Safe_Str__Bisect_Term` | valid terms, uppercase/space/empty/33-char rejected |
| `tests/unit/core/actions/bisect/test_Vault__Bisect__Graph.py` | `Test_Vault__Bisect__Graph` | candidates, weights, best, skip_away vectors, estimate_steps vectors, merge_bases, first-parent, pathspec, boundaries |
| `tests/unit/core/actions/bisect/test_Vault__Bisect__Graph__Git_Oracle.py` | `Test_Vault__Bisect__Graph__Git_Oracle` | 9.3 |
| `tests/unit/core/actions/bisect/test_Vault__Bisect__Working_Copy.py` | `Test_Vault__Bisect__Working_Copy` | writes/deletes only the diff, dirty guard, carry-over, selective, scoped, crash recovery |
| `tests/unit/core/actions/bisect/test_Vault__Sync__Bisect.py` | `Test_Vault__Sync__Bisect` | the command flows (9.2) |
| `tests/unit/core/actions/bisect/test_Vault__Bisect__Runner.py` | `Test_Vault__Bisect__Runner` | exit-code mapping, 126/127 rule, abort, timeout, env, argv vs `--shell` |
| `tests/unit/core/actions/bisect/test_Vault__Bisect__Log.py` | `Test_Vault__Bisect__Log` | render, parse, hostile lines refused, replay equals the original |
| `tests/unit/core/actions/bisect/test_Bisect__Refusals.py` | `Test_Bisect__Refusals` | every row of 7.1 |
| `tests/unit/core/actions/bisect/test_Bisect__Nothing_Leaves_The_Clone.py` | `Test_Bisect__Nothing_Leaves_The_Clone` | 6.3 |
| `tests/unit/core/actions/bisect/test_Bisect__No_Write_Calls.py` | `Test_Bisect__No_Write_Calls` | source grep, 6.3 |
| `tests/unit/cli/test_CLI__Bisect.py` | `Test_CLI__Bisect` | parsing, custom terms, text and `--json`, exit codes |
| `tests/unit/cli/test_CLI__B07__Namespace_Moves.py` | (existing) | unchanged: no top-level command added; the test must still pass |
| `tests/security/test_Security__Fixed__Bisect.py` | `Test_Security__Fixed__Bisect` | hostile replay file, state naming an unknown commit, a path in state outside the tree, `run` never via a shell without `--shell` |

### 9.2 Cases (the synthetic histories)

Helper `Bisect__History_Builder` (in `tests/_helpers/`, a class) builds a vault with commits whose content is
known: commit `ck` writes `f.txt = k`; from commit `c11` on, `bug.txt` exists. The oracle command is
`test ! -f bug.txt` (or a Python equivalent for Windows CI).

| # | Case | Expect |
|---|---|---|
| 1 | linear 16 commits, `start c16 c1`, marks by hand | steps c8 → c12 → c10 → c11; `c11 is the first bad commit`; 4 steps; each "Bisecting" line equals Git's numbers (7/3, 3/2, 1/1, 0/0) |
| 2 | same with `run` | exit 0, same sequence, `runs` has 4 entries |
| 3 | `start` with nothing, then `bad`, then `good c1` | waiting messages in Git's words; first checkout only after both |
| 4 | merge graph (m1, m2, side b1–b3, m3, m4, merge m5, m6), bug in b2 | first step b3 (Git's choice, 9.3), result b2 |
| 5 | same, `--first-parent`, bug in b2 | first step m3; result m5 (the merge that brought it), as Git |
| 6 | skip the first proposed commit (c8) | next c9 (index 0); skip again → index 6 rule applied |
| 7 | all remaining candidates skipped | `ONLY_SKIPPED`, `possible` lists them; `run` exits 2 |
| 8 | `run` command exiting 125 everywhere | `ONLY_SKIPPED`, exit 2 |
| 9 | `run` exiting 128 / killed by a signal | stops, state kept, exit 128 / 128+n |
| 10 | `run` command not found (127 on every commit) | `bogus exit code 127 for good revision`, exit 1, state kept |
| 11 | `run` exiting 127 only on bad commits | treated as bad; result correct |
| 12 | good not an ancestor of bad (bug fixed on a side branch) | merge base tested first; a bad merge base stops with Git's message and the terms hint |
| 13 | custom terms `--term-old broken --term-new fixed`, `sgit history bisect fixed` | finds the fixing commit |
| 14 | invalid terms (`start`, equal terms, uppercase) | refused |
| 15 | pathspec `-- docs/` with commits touching other folders | only commits touching `docs/` tested; result equals Git's with the same pathspec (linear) |
| 16 | dirty file the next step changes | refused before writing, path named; working copy and state unchanged |
| 17 | dirty file the next step does not touch | carried over across steps and through reset |
| 18 | untracked file at a path the step creates | refused (`blocked_targets`) |
| 19 | process killed between transition write and completion (simulate by writing the transition and half the files) | next command finishes the move; content equals the target commit |
| 20 | `reset` after found | working copy equals the clone head byte for byte; `bisect.json` gone; clone ref, reflog unchanged |
| 21 | `reset <commit>` | working copy at commit; clone ref moved; one reflog entry |
| 22 | damaged `bisect.json` | `reset` refuses listing differing paths; `reset --force` restores the head |
| 23 | `log` then `replay` in a fresh bisect | same state, same current commit |
| 24 | replay file with `run rm -rf …`, shell metacharacters, unknown ids | refused lines named; nothing executed |
| 25 | selective clone (`--no-checkout`, two files checked out) | steps write only those two when changed; checkout record correct after reset |
| 26 | scoped clone (`--path a`) | default pathspec = scope; commits changing only `b/` never tested |
| 27 | shallow clone `--depth 5`, bug older than the boundary | first bad reported "at the boundary", `at_boundary: true` |
| 28 | read-only clone | full bisect works; nothing written to the host |
| 29 | pack vault and pack-store clone | same results as loose; no download during steps |
| 30 | `--no-checkout` | working copy bytes never change; `sgit cat` returns the commit under test's bytes; `SGIT_BISECT_COMMIT` set in `run` |
| 31 | each refused command of 7.1 | refused with the bisect message; nothing changed |
| 32 | status during bisect | compares with the commit under test (clean right after a step) |
| 33 | the clone head moved by a second process during the bisect | warning once; reset returns to the new head |
| 34 | 6.3 snapshot test | host store, refs, baselines, index, reflog byte-identical |

### 9.3 Git as the oracle

`Test_Vault__Bisect__Graph__Git_Oracle` builds the same commit graph in a scratch Git repository (`git init`,
fixed author/committer dates) and in an sgit vault, runs `git bisect start/good/bad` and sgit's
`Vault__Bisect__Graph.best`, and compares the **position** of the chosen commit (its message `ck`, since ids
differ). Graphs where the choice is tie-free or where the tie rule is known to agree:

| Graph | Git's choice *(run here)* |
|---|---|
| 16 linear, good c1, bad c16 | c8, then (good) c12, then (bad) c10, then (good) c11 |
| merge graph of case 4, good m1, bad m6 | b3 |
| same, `--first-parent` | m3 |
| 16 linear, skip c8 | c9 |

Also compared: the "N revisions left (roughly S steps)" numbers for each step, and the final "first bad commit"
on cases 1, 4, 5, 13, 15. Skip picks after the first are not compared with Git (Git's order among equal
distances is SHA-1 order); `skip_away` is tested against the formula vectors in 5.5 instead.

### 9.4 Acceptance checklist (implementation and deployment)

- [ ] `sgit history bisect --help` lists every subcommand of 3.1; `sgit help all` unchanged at the top level;
      `test_CLI__B07__Namespace_Moves` passes.
- [ ] Case 1 by hand on a real clone: four steps, Git's numbers, `c11 is the first bad commit`.
- [ ] Case 2 (`run`) exit 0; case 7 exit 2; case 9 exit 128; case 10 exit 1.
- [ ] Git-oracle tests pass (9.3).
- [ ] After `reset`, `sgit status` is clean and `sgit history reflog` has no new entry; `.sg_vault/local/bisect.json`
      does not exist.
- [ ] 6.3: host store and local refs byte-identical across a full `run`; the source-grep test passes.
- [ ] Every command in 7.1's "refused" rows refuses with the bisect message and changes nothing.
- [ ] Dirty-file guard: case 16 refuses, case 17 carries.
- [ ] Selective, scoped, shallow, read-only, pack, pack-store cases pass (25–29).
- [ ] `--no-checkout` mode: working copy untouched; `sgit cat` follows the commit under test.
- [ ] Crash recovery (case 19).
- [ ] Security tests in `tests/security/test_Security__Fixed__Bisect.py` pass; threat-model rows added.
- [ ] `pytest tests/unit/ -n auto` and `pytest tests/security` green; bandit baseline unchanged except the
      runner's `subprocess` lines, each with a `# nosec B603` justification like `Container__Command_Runner`.
- [ ] Measured on the 76,000-file synthetic vault: `start` and per-step times with and without `--no-checkout`,
      in the CHANGELOG.
- [ ] CHANGELOG `[Unreleased]` entry; README "Git commands → sgit" table gains bisect.
- [ ] On the dev pre-release (`pip install --pre sgit-ai`): run case 1 against the live dev API with a scratch
      vault; confirm with the API's object listing that the vault's files did not change during the bisect.

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `feat(bisect): state and types` | 5.1 types, schemas, `Vault__Bisect__State`, errors; schema and state tests | 0.5 day |
| 2 | `feat(bisect): graph — candidates, weights, midpoint, skip` | `Vault__Bisect__Graph` without pathspec; graph tests, formula vectors, Git oracle (linear, merge, first-parent, skip) | 1 day |
| 3 | `feat(bisect): move the working copy between commits` | `Vault__Bisect__Working_Copy`; guard, selective, scoped, crash recovery tests | 1 day |
| 4 | `feat(bisect): start / good / bad / skip / next / reset / terms / status` | `Vault__Sync__Bisect`, `CLI__Bisect`, registration; flows 1, 3–7, 12–14, 16–23, 31–33 | 1 day |
| 5 | `feat(bisect): run, log, replay, view, --no-checkout` | runner, log, view, the working-commit hook in status/cat/ls/checkout; cases 2, 8–11, 23–24, 30 | 1 day |
| 6 | `feat(bisect): pathspec, scoped default, shallow boundary, pack generations` | `touches_paths`, cases 15, 25–29; optional index-pack generations | 0.5–1 day |
| 7 | `feat(bisect): refuse other commands during a bisect; security tests; docs` | the `check_not_in_progress` calls (5.10), 6.3 tests, security tests, threat-model rows, CHANGELOG, README, the 76k measurement | 0.5–1 day |

Total: about 5–6 days. The roadmap's "1–2 days" covered the core loop only; the clone shapes, the refusals and the
no-write proof are most of the work.

---

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Commits during a bisect | (a) refuse; (b) allow, as Git does on a detached HEAD (where `reset` orphans them) | **(a) refuse.** In sgit a commit moves the clone branch itself, so "allow" would mean committing an old tree onto the branch: a silent revert |
| D2 | Custom-term syntax | (a) exact Git syntax (`sgit history bisect fixed`) via one REMAINDER parser and our own dispatcher; (b) fixed argparse sub-parsers plus `mark <term>` | **(a)**: Git parity, and bisect's grammar is small enough to dispatch by hand; `--help` text is written by `CLI__Bisect` |
| D3 | `run` and the shell | (a) argv by default, `--shell` opt-in; (b) always a shell, as Git | **(a)**. Same power (`--shell 'make test && ./check'`), no surprise interpretation of a file name |
| D4 | Pathspec on merges | (a) the approximation in 5.3 (a merge counts when it differs from every parent); (b) port Git's full history simplification | **(a)** now; it equals Git on linear history and is documented. Revisit if someone bisects path-limited merge-heavy histories |
| D5 | `--timeout` result | (a) abort the run (state kept, exit 124); (b) count as skip | **(a)**: a hang usually means the test is broken, not the commit; skip would quietly widen the answer |
| D6 | What `history log` shows during a bisect | (a) the clone head (unchanged); (b) the commit under test, like Git's `git log` on a detached HEAD | **(a)**, plus `bisect view`; keeps `history log` meaning "my branch" |
| D7 | The existing `branch checkout <commit>` "detached" mode (`CLI__Vault.py:1567`) | (a) leave it; (b) re-implement it on this design's working-commit state (`working_commit` with a reason `checkout`), so status, commit and reset understand it | **(b), as a separate follow-up**: today it writes every file with no dirty check and makes the next commit a silent revert. Bisect lays the groundwork (state file, diff-only moves, refusals) |
| D8 | `reset` with dirty files | (a) refuse unless `--force` (sgit default); (b) carry over silently like Git | **(a)** for files the move would overwrite, carry the rest. Same rule as pull |
