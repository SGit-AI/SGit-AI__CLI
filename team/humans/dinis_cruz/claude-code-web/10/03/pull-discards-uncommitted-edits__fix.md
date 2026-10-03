# Fix — `sgit pull` silently discarded uncommitted edits to tracked files

**Date:** 2026-10-03
**Branch:** `claude/charming-babbage-5hzcxq` (restarted from `dev` @ `2f86cf5` after PR #6 shipped as 0.17.0)
**Bug report:** RiskMandate.ai agent team (@briefs), 3 Oct 2026 — hit three times in real use on a
vault shared by ~10 agents. Reproduces on 0.16.0 and 0.17.0, so not a regression from the clone work.

## 1. Root cause

`Step__Pull__Merge` applied the result of a fast-forward by calling
`_checkout_flat_map(directory, theirs_map, …)` with the **whole** incoming tree, and the
three-way path did the same with `merged_map`. Both maps are built from committed trees
(clone HEAD, named HEAD, LCA), never from the working directory, so every tracked file was
rewritten from its committed blob — including a file the user had edited and not
committed, and including files the incoming commits never changed. `status` then compared
the (now reverted) file with HEAD and found nothing to report: "fully in sync". The edit
was simply gone.

## 2. The fix — git's rules, applied before any write

`sgit_ai/core/actions/pull/Vault__Pull__Guard.py` (new) and `_guard_working_tree` in
`Step__Pull__Merge`:

1. Scan the working tree with the same ignore-aware scanner `status` uses
   (`_scan_local_directory`) and classify each path against the clone HEAD tree:
   `modified` (content hash differs), `deleted` (tracked, absent on disk; on a sparse clone
   an unfetched blob is not "deleted"), `untracked` (on disk, not in HEAD).
2. For each dirty path, ask "does the merged tree's blob for it differ from HEAD's blob?":

   | working tree | merge leaves it as HEAD | merge changes it |
   |---|---|---|
   | modified | **carry over** — not written, edit survives | **refuse** |
   | deleted | **carry over** — stays deleted | **refuse** |
   | untracked, incoming creates same path | identical content → fine | **refuse** (would overwrite) |
   | untracked, not incoming | ignored | — |

3. Any refusal raises `Vault__Dirty_Working_Tree_Error` **before** `_checkout_flat_map`,
   `_remove_deleted_flat` or the clone-ref write, naming each path and why. The working
   tree, the clone ref and the object store are exactly as before the command.
4. Otherwise the checkout writes `merged_map` minus the carried-over paths. Removal
   (`_remove_deleted_flat`) only touches paths absent from the merged tree, so a carried
   file is never deleted either.

CLI: the refusal prints as
```
error: your local changes would be overwritten by pull:
  x.txt  (your uncommitted edit would be overwritten)
commit them (sgit commit) or stash them (sgit vault stash) and pull again; nothing was changed
```
and a successful pull that carried edits adds
```
Kept 1 uncommitted change(s) the incoming commits did not touch:
  ~ y.txt  (yours, uncommitted)
```
(`kept_dirty` in the pull result dict / `kept_dirty_files` on `Schema__Pull__State`).

Three-way merges get the same guard; a conflict on a dirty path is "changed by the merge"
and refuses, so no `.conflict` file is ever written over uncommitted work.

## 3. Tests (`tests/unit/workflow/pull/test_Pull__Dirty_Working_Tree.py`, two real clones on the in-memory API)

- the reported case: Bob changes `x.txt`, Alice has an uncommitted `y.txt` → pull merges
  `x.txt`, keeps `y.txt`, status still shows `~ y.txt`
- dirty `x.txt` while Bob changed `x.txt` and `docs/z.md` → refused, **neither** file
  changed, clone ref unchanged; after `commit` the same pull merges
- locally deleted untouched file stays deleted; locally deleted file Bob changed → refused
- untracked `new.txt` colliding with Bob's `new.txt` → refused; identical bytes → fine;
  unrelated untracked file left alone
- clean tree: unchanged behaviour, `kept_dirty == []`
- three-way: dirty untouched file survives; dirty file the other side changed → refused
- unit tests of `plan()` rules, `dirty_paths()` semantics, the message
- CLI: the error renders without the fsck/corruption hints; the `Kept` block renders

## 4. Minor issue 1 from the report — `status` said "200 ahead, 1 behind"

Real, and I had seen it myself on a fresh clone. Two things were wrong in `status`:

1. It **overwrote the local named ref with the remote value first**, then counted. When
   the remote had moved, the local ref pointed at a commit the store did not have, the
   ancestor walk from it was empty, and `clone_walk − named_walk` was the entire local
   history — "N ahead" on a clone with no unpushed commits, plus the hint "push your own
   commits". Every later `status` walked from the same hole.
2. It had no way to get the missing commits.

Now `status`:

- reads the remote ref **without writing it**, and keeps the local ref as
  `last_known_named_head` — the remote head whose history this clone fully has (set by its
  last push/pull, or by a status that fetched completely);
- walks the commit graph from the remote head, fetching the commit objects that are absent
  (one ~700-byte object per new commit, verified before write — the same path pull uses),
  bounded by `commit_fetch_limit` (default 50), and reports whether the chain **connects**
  to local history (a local head whose parents are missing is not connected — my first
  version used "head exists" and gave a short count; a test caught it);
- advances the local named ref only when connected;
- when connected: exact `ahead` / `behind`. When not (offline, or more than the limit of
  new commits): `ahead` = local commits not reachable from `last_known_named_head` (still
  exact — it never needed the network), `behind` = what was fetched, flagged
  `behind_lower_bound`, which the CLI prints as `50+ new commits`.

Tests: fresh clone one behind → `(0, 1, 'behind')`; diverged 1/2 → `(1, 2, 'diverged')`;
offline with one unpushed commit → `(1, 1+, 'diverged')`; three new commits with the limit
at 1 → lower bound, then exact `(0, 3)` once the limit allows.

Cost: the walk is bounded (2,000 visited; `_count_unique_commits` was already bounded at
200), and the fetch happens only for commits the store lacks, so a `status` on an
up-to-date clone makes the same single ref read it made before.

Minor issues 2 (doctor `whoami` on the dev server) and 3 (read key + wrong vault id message)
are not touched here: the first is server-side, the second is a wording change on a path
that already lists "the vault key or ID is incorrect" as cause 1.

## 6. Replication and side effects (asked after the first push)

**The new tests reproduce the bug on the pre-fix code.** With the four changed source files
checked out from `dev` and the new test file run unchanged: 10 of 17 fail, the reported case
on `assert 'y v1' == 'y v2 (UNCOMMITTED in A)'` (the edit reverted), every refusal test on
`DID NOT RAISE`, and the status tests on the old numbers — a fresh clone one behind reported
`(2, 1, 'diverged')`. With the fix: 19 of 19 pass (two status tests added since).

**Side effects of the pull guard, considered:**

- *Pull can now refuse where it used to "succeed".* A script that edits a file, then pulls
  while another agent changed the same file, now exits 1 with the paths named instead of
  silently losing the edit. That is the intended change; an agent loop should commit (or
  `sgit vault stash`) before pulling, which is what git demands too. A `--autostash` flag
  would be the convenience to add if the teams want it.
- *Cost:* the guard hashes the working tree exactly as `status` does. Measured on the
  2,900-file DC vault clone: 393 ms for the 1,687 scanned files (13 MB). It runs only when
  a pull actually merges, never on an up-to-date pull.
- *Carried-over edits after a fast-forward* are dirty against the new HEAD exactly as they
  were against the old one (same blob), so `status` shows them and the next `commit`
  includes them — the same as git.
- *Three-way merges* create the merge commit from committed trees only; a carried-over edit
  stays uncommitted on top of it, as in git. A conflict on a dirty path refuses before any
  `.conflict` file is written.
- *Sparse clones:* an unfetched tracked file is not "deleted" (same rule `status` uses), so
  sparse pulls behave as before; the sparse suite passes unchanged.
- *Ignore rules:* the scan is the ignore-aware one `status` uses, with tracked paths exempt
  from ignore ("tracked wins"), so a tracked-but-ignorable file is never misread as deleted.
- *Untracked collisions* now refuse (git does too); identical bytes pass. Previously the
  local file was overwritten silently.
- *API surface:* `kept_dirty` is a new key in the pull result dict and `kept_dirty_files`
  a new field on `Schema__Pull__State`; both default empty, nothing reads them strictly.

## 5. What I could not do from here

The report's `repro.sh` needs an access token for `dev.send.sgraph.ai`; this session has
none, so the end-to-end check is the two-clone test above, which follows the script
step for step. Running `repro.sh` against a release with this fix should end with
`RESULT: OK, uncommitted edit kept`.
