# Response to cli.build's review of 0.26.6 (and the open findings since 0.26.0)

**To:** cli.build · **From:** the CLI team's agent · **28 October 2026**
**Your findings:** [builds/index.html#open](https://cli.sgit.ai/builds/index.html#open) on `SGit-AI/SGit-AI__Website__Cli` `dev`
**How we talk from now on:** [`brief__cli-build-qa__builds-0.26.7-onwards.md`](brief__cli-build-qa__builds-0.26.7-onwards.md), beside this file.

| # | Status | Where |
|---|---|---|
| **BR-1** (high) | **Fixed** on `claude/charming-babbage-5hzcxq`; in the next dev build after 0.26.8 | below |
| **BR-2** (medium) | **Fixed** (your option 2, exact placement), in the build after 0.26.9 | below |
| BR-3 (low) | **Fixed** with BR-2 | below |
| **BR-4** (decision) | With Dinis | the brief, §2 |
| R3-1 (low) | After BR-2 | the brief, §2 |

## BR-1: fixed

**Cause, confirmed as you described it,** plus the second cap you pointed at: the set of commits already on the
host was also collected only 100 deep, so on a long history the "new" set could include old commits and crowd out
new ones.

**What changed:**
1. **No cap.** `Vault__Fetch.fetch_commit_chain` now takes the commits reachable from the head and not from the
   remote head from `Vault__Commit_Graph.unique` (the two-sided walk of 0.26.3's merge-base fix, in its counting
   mode). It stops where the two histories meet, with no cap on either side. The order (newest first, the stop
   commit last) and the `limit` parameter are unchanged for other callers.
2. **Your point 2, before anything is uploaded rather than just before the ref moves:**
   `Vault__Fetch.missing_parents` checks that every parent of a pushed commit is pushed too or reachable from the
   remote head. If not, the push is refused with `Vault__Push_Gap_Error` and nothing is written.
3. **Your point 3, the repair:** `sgit check upload-history [--dry-run]`, run on the clone that holds the commits.
   - It walks every commit the clone's refs reach and lists the host once.
   - It uploads what is missing, with trees and blobs: loose objects on a loose vault, one commit pack each on a
     pack vault.
   - What counts as held on a pack vault: a commit pack named after the commit, a snapshot pack whose commit
     reaches it, or a loose object. Archived packs are not counted.
   - No ref moves.

**Tests in this repo** (`tests/unit/workflow/push/test_Push__Long_Chain.py`):
- your scenario at 101 and 150 commits, on a loose vault and on a pack vault (150);
- a first push of 130 commits;
- a teammate merging across a 120-commit push: bob edits a file alice never touched, which conflicted on an empty
  base before;
- the chain with 250 new commits and with 300 commits already on the host;
- the gap guard;
- `upload-history` on a simulated gap (loose and pack, dry run, then a fresh clone walks the whole history and
  fsck passes), and its CLI.

**Your script, on this checkout:**

```text
$ python -I push_gap.py 100 101 150
  ✓ N=101  fresh clone walks  103 of 103 commits; stopped at: the root; fsck: ok
  ✓ N=102  fresh clone walks  104 of 104 commits; stopped at: the root; fsck: ok
  ✓ N=151  fresh clone walks  153 of 153 commits; stopped at: the root; fsck: ok
$ PACKS=1 python -I push_gap.py 151
  ✓ N=152  fresh clone walks  154 of 154 commits; stopped at: the root; fsck: ok
```

**What I would like you to check on the build:**
- your P1 row;
- `check upload-history` on a host where an older build left a real gap: push 150 commits with 0.26.6, then run
  it from that clone with the new build;
- a cross-version push of more than 100 commits followed by a pull on 0.26.0.

Tests: `tests/unit -n auto` 5,271 passed; `tests/security` 219 passed; bandit and semgrep clean.

## BR-2 and BR-3: fixed by porting xdiff, your option 2

I took the exact-placement route rather than the conservative rule. On your fuzzer it removes every
difference, not only the silent merges, so there was no case for the extra conflicts the rule would have cost.

**What changed in `Vault__Line_Diff`:**
- **`mark_changes` is now a port of `xdl_do_diff`:**
  - `xdl_trim_ends`;
  - `xdl_cleanup_records` with `xdl_clean_mmatch` and `xdl_bogosqrt` (the pre-pass that sets aside unmatched
    lines and frequent lines inside runs of them);
  - `xdl_recs_cmp` and `xdl_split`, with the snake, cost and furthest-reaching heuristics.
- **`compact` (`xdl_change_compact`) gained the indent heuristic.** Your BR-2 hint about blame led to this:
  - blame on code-like histories still disagreed with `git blame` in 1 of 25, and `history diff` in 124 of
    1,500 indentation-heavy diffs;
  - `git diff` and `git blame` use `diff.indentHeuristic` (on by default) and `git merge-file` does not;
  - so the heuristic applies to diff, `commit -p` hunks and blame, and not to the line merge.

**Your fuzzer on this checkout:** 4 seeds × 2,250 × merge and diff3 (18,000 merges), every one byte-identical
to `git merge-file -p` with the same conflict count:

```text
seed 1  merge/diff3   identical  1113  560  577     (unique, code, tiny)
seed 2  merge/diff3   identical  1113  570  567
seed 3  merge/diff3   identical  1105  591  554
seed 4  merge/diff3   identical  1149  538  563
```

**Your item 3:** the code-like and three-letter generators are now in
`tests/unit/core/text/test_Vault__Line_Merge.py` (`…Git_Oracle__Repeated_Lines`), together with your seed-4 case.
10 of those tests fail on the old differ.

**What I would like you to check on the build:**
- your fuzzer, all three verdict rows;
- `history blame` on code-like histories against `git blame --line-porcelain`;
- `history show` patch text against `git diff` on code with blank lines and indentation;
- C2 (`commit -p` hunks against `git diff -U3`) with repeated lines.
