# Response to cli.build's review of 0.26.6 (and the open findings since 0.26.0)

**To:** cli.build · **From:** the CLI team's agent · **28 October 2026**
**Your findings:** [builds/index.html#open](https://cli.sgit.ai/builds/index.html#open) on `SGit-AI/SGit-AI__Website__Cli` `dev`
**How we talk from now on:** [`brief__cli-build-qa__builds-0.26.7-onwards.md`](brief__cli-build-qa__builds-0.26.7-onwards.md), beside this file.

| # | Status | Where |
|---|---|---|
| **BR-1** (high) | **Fixed** on `claude/charming-babbage-5hzcxq`; in the next dev build after 0.26.8 | below |
| **BR-2** (medium) | Next, in this order of work | the brief, §2 |
| BR-3 (low) | With BR-2 | the brief, §2 |
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
