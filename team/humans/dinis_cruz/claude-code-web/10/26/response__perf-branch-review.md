# Response: "The performance branch, reviewed" (cli.sgit.ai QA, 26 Oct 2026)

**Review:** `b6a38300-sgit-perf-branch-review.md`, of `claude/charming-babbage-5hzcxq` at `c6c4818`.
**Verdict on the verdict:** correct on every finding. The blocker (finding 1) was real and reproduced here with all
three of the review's repros; the fix is the one the review proposed, plus the belt-and-braces guard on pull. The
branch had already been merged to dev as **v0.24.1 before the review arrived**; that tag is dev-only (not on PyPI),
and this commit supersedes it. Every finding is fixed with the test the review asked for.

## 1. Findings and what changed

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | HIGH. A same-size edit with the mtime restored was invisible: `commit` skipped it, `pull` overwrote it | The cache entry is git's index key: `[mtime_ns, ctime_ns, size, ino, dev, hash]`. A restored mtime leaves ctime moved (no user-space call sets it back); a same-size `mv` over a file changes the inode. Format version 2; the 0.24.1 format is discarded whole. **And** the pull's dirty-tree guard passes the paths the merge would write or delete to the scan as `verify`: those are read and hashed whatever the cache says. It is a handful of files, and the one place a missed edit destroys data | repros 1, 2, 3 verbatim, plus a forged cache entry that matches the edited file's stat exactly: the scan trusts it, the pull guard still reads the file and refuses |
| 2a | HIGH. Racy window measured from now, not from the scan | An entry is recorded only when the file's mtime is more than 2 s before the **scan's start**, and trusted on the same rule. Two same-size writes in one tick of a coarse filesystem: the first is never recorded | a file written just now is absent from the cache; aged, it is recorded |
| 2b | HIGH. Hash taken, then stat: a save in between pairs the old hash with the new size | The stat taken **before** the read (the link check's `lstat`) is the one recorded, only if the stat after the read is identical and the content length is the stat's size; otherwise the hash is used this time and not cached | an atomic save between read and stat (a guard subclass): no entry, re-read next time |
| 2b | The phantom (`~ notes.txt` for ever) | Cannot arise once no entry pairs a stale hash with a fresh stat. Commit does not write hashes back: the scan it runs already records every file it read | covered by the above |
| 3 | MEDIUM. `_commits_between` listed old history after a merge with a clock behind | The base's whole ancestry is collected first (commits only; bounded at 50,000), then head's reachable commits minus that set, sorted by date. Exact for any clock | the review's graph: B(5) on A(10), H = merge(X(12), B): `[H, X]` |
| 4 | LOW-MEDIUM. `diff_trees` matched by ciphertext name | Entries are matched by decrypted name (`_entries_by_name`), decrypting only in the trees that differ, so the pruning stands | a tree written with `encrypt_metadata` (random IV): one added file reads `+1` |
| 5 | LOW. Flat cache not fail-safe | Format version 2 (a file without it is a miss); any exception reading it is a miss; every `blob_id` and tree id is checked against `OBJECT_ID_RE` on read; a stale `.tmp` is pruned with the old heads. Plus one tree read per hit: the root tree's files and folders must match the cache's root level, so an emptied or truncated file is a miss. A cache edited below the root is not caught: its folder is the key's folder (TM-R41) | non-dict entries, a poisoned blob id, an emptied `flat`, an emptied `dirs`, a missing version, a stale `.tmp` |
| 6 | LOW. Branch switch recorded a head as accepted with blob fetches possibly failed | The baseline is written only when `_find_missing_blobs` is empty, the pull path's own check | by reading; the pull-skip tests cover the record's meaning |
| 7 | LOW. TM-R41's premise ("already in the working tree") | Row corrected: `history diff --commit <old>` caches the old tree (a deleted file's name can sit there until two newer heads push it out) and a sparse clone caches names it never fetched. The row now states the sealed-vault-keys condition: when nothing else in `local/` is in clear, the caches go too (encrypted under a key derived from the read key, or memory only) | — |

Cost of the fixes, on the synthetic vault (228,000 files): `status` 7.4 s cold process, 7.0 s warm, against 7.1 s
and 6.3 s before the review (the key is five integers the `lstat` already returned; the root check is one tree
read). A clone that ran 0.24.1 pays one status that reads every file (116 s here) while the v1 cache is replaced.
A pull reads the files it is about to change.

## 2. Two notes on the review's method

- The fuzzer (16 seeds, 430 commits, every head against a canonical rebuild) is the right test for the incremental
  build and it is more than the branch's own nine shapes. If it can be run as a job against each dev tag, as for
  pack mode, that would be the standing check for this code.
- "Every other finding can ride" was right, and every other finding is in this commit anyway: each was a small
  change with a test the review had already written in prose.

## 3. Files

`sgit_ai/core/Vault__Sync__Base.py` (scan cache v2: key, racy rule at save and at hit, stat before and after,
`verify`), `sgit_ai/workflow/pull/Step__Pull__Merge.py` (touched paths verified), `sgit_ai/core/actions/pull/
Vault__Sync__Pull.py` (`_commits_between` exact), `sgit_ai/storage/Vault__Sub_Tree.py` (diff by decrypted name;
flat cache version, validation, root check, `.tmp` pruning), `sgit_ai/core/Vault__Sync.py` (branch-switch baseline),
threat model TM-R41. Tests: `tests/unit/sync/test_Vault__Sync__Scan_Cache__Review_10_26.py` (12 tests, one per
repro and hole), `test_Vault__Sync__Scan_Cache.py` and `test_Vault__Sub_Tree__Flatten_Fast.py` updated to the
new formats, `Known_Gaps` TM-R41 ages its file past the racy window.
