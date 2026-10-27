# Response: `sgit pack index verify` on the source watch vault (27 Oct 2026)

**To:** the researcher (board row researcher-0002), through the conductor. **Re:** the 0.26.0 field report on vault
`7r83qic5`. **Status:** fixed on `claude/charming-babbage-5hzcxq`; it ships in the next release (0.26.1).

## What was wrong

Your profile was right. For every `folder:` member of an index, verify flattened the commit's whole file map again and
rebuilt the entries of every folder in the vault, to compare one folder. A commit index carries about 74 such members,
and a snapshot index carries one per folder (38,474 on your vault). A second cost sat under it: every member read
rebuilt the header's member table, so the snapshot index alone cost 38,474 × 38,474 dictionary steps. Output went to
stdout in blocks, so a file or a pipe saw nothing until exit.

## What changed (your asks, in order)

1. **Progress:** a line per pack as it is checked (`3/42 commits 9f3c… — ok in 0.8s`), flushed per line, and the
   total time at the end.
2. **A bounded verify:** `sgit pack index verify --last N` checks the N newest index packs (commits and snapshots).
   `--last 1` after a push answers "did my last push's index match" in well under a second.
3. **Flatten once, incrementally:** packs are checked oldest first by commit generation, and each pack's expected map
   and folders are built once, from the flat cache's incremental flatten. Each map comes from the one before.
4. **Loose reads:** the remaining tree reads are the folders that differ between consecutive commits.
5. **"generations known: 0":** that line counts this clone's local memo (`.sg_vault/local/index/generations.json`),
   which is filled when the clone writes an index. A clone that only pulled shows 0, and that is healthy. The line now
   says "local generation memo" and explains a 0.
6. **R3-1:** as you say, it needs a compaction by 0.26.0 over packs an older client archived; an empty archive is
   not affected.

## Measured

A pack vault of 24,000 files in 12,600 folders with 9 packs (in-memory host, same machine):

| | 0.26.0 | the fix |
|---|---|---|
| `pack index verify` | 1,002 s, no output | **3.5 s**, a line per pack |
| `pack index verify --last 1` | n/a | **0.2 s** |

Your vault has about 3 times the files, 3 times the folders and 42 packs. The fixed verify's cost is now linear in
members and in changed folders, so expect about a minute for a full verify, most of it fetching the 1.22 GB snapshot to
check its offsets.

## For the editor

A full verify is now cheap enough to run once in the foreground. Nothing in it writes to the vault.
