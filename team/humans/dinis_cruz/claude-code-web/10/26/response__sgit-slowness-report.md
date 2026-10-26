# Response: "sgit 0.24.0 is slow on a large pack vault" (newsroom, 26 Oct 2026)

**Report:** `d41c5325-sgit-slowness-report.md` by researcher@php.newsroom, measured on the source watch vault
`7r83qic5` (79,465 files, 38,474 folders, 2.7 GB; 176,093 loose objects locally).
**Answer in one line:** every number in the report has a root cause in the client, all are fixed on the branch,
and no vault key was needed — the shape of the vault was enough to reproduce it synthetically.

## 1. The report was right, and more

The profile in the report pointed at `Vault__Sub_Tree.flatten` and `Type_Safe.from_json` (85% of a status). That
was the biggest item, not the only one. On a synthetic vault of the same shape, three times the files (228,000
files in 38,000 leaf folders, 77,227 trees, 305,230 objects), the time went to:

| command | where the time was | root cause |
| --- | --- | --- |
| `status` | flatten ×2 (two minutes each), then the scan reading and hashing every file | `Type_Safe.from_json` per tree; no index |
| `commit` | the tree builder, then flatten | a quadratic scan of folders for each folder's children (47 minutes for the first commit of the synthetic vault); every tree rebuilt and re-encrypted whatever changed; every file read again |
| `push` | the implicit pull's object walk, then a status, then a second walk of the working tree | every tree of the server's head loaded through `Type_Safe`, twice, even with nothing new on the server |
| `history log` | one full flatten per commit | the `+N ~M` counts |
| the scan itself | `Vault__Path_Guard().is_protected` per path (a `Type_Safe` object each), 2 million segment normalisations, ancestor ignore rules per file, two `lstat`s per file | per-call construction, no memoisation |

All five suggestions in the report are in, in substance:

1. flatten once per command → once per head: the flattened head is cached per process and on disk, keyed by tree id;
2. cache the flattened HEAD in `.sg_vault/local/` → `flat-cache/<tree id>.json`, plus `scan-cache.json` (git's index rule: size + mtime, 2 s racy window);
3. load a tree as a plain dict → `_load_tree_entries` reads the JSON and checks every id against the object-id form;
4. push should not walk everything first → the implicit pull skips the walk when the server's head is the one this clone last accepted (the record is written only once every object was local), and the status it runs is the fast one;
5. `history log` should not flatten per commit → it diffs each commit against its parent, walking only where tree ids differ.

And two the report could not see from a status profile: the quadratic tree builder, and the commit that rebuilt
every tree. A commit now keeps an unchanged file's entry without reading the file, and an unchanged folder's tree
id without rebuilding it (checked to be in the local store), so a one-file commit builds the five or six trees on
that file's path. Tests prove the incremental build gives exactly the ids a full build gives, for a modified file,
added and deleted files, a rename, a new folder chain, a folder emptied, a file that became a folder and back, a
same-size edit, and an old tree missing from the store.

## 2. Numbers

Synthetic vault, 4-core sandbox, in-memory host (so network time is excluded; the newsroom's figures include it).
"0.24.0" is the package as released, run on the same vault.

| command | 0.24.0 (newsroom vault) | 0.24.0 (synthetic, 3× the files) | branch (synthetic) |
| --- | --- | --- | --- |
| `status`, nothing changed, cold process | 155 s | 130 s | 7.1 s |
| `status`, warm process | — | 139 s | 6.3 s |
| `commit`, one file | 4 min 11 s – 4 min 24 s | first commit: 47 min (2,846 s) | 9.3 s |
| `push`, one small commit | ~4 min 15 s | — | 9.8 s (2 commits), 18 s under cProfile |
| `history log`, 10 commits with counts | > 8 min | 464 s | 7.4 s |
| first commit of the whole vault | — | 2,846 s | 155 s |
| first push (snapshot of 305k objects) | — | — | 130 s |

Where the remaining seconds go: a status is now one `os.walk` of 77k folders with one `lstat` per file (about
4 s of the 7), reading the scan cache and the flat cache (JSON, ~1.5 s each), and the ignore rules. A commit is a
status plus the trees on the changed paths. A push is a status, the pull's ref check, and the upload.

## 3. What this changes on disk, and the security note

Two new files under `.sg_vault/local/`, both 0600, both derivable from the working copy and the store with the
read key:

- `flat-cache/<tree id>.json`: the head's paths, sizes, content hashes, content types, and the tree id of every
  folder. Newest two heads kept.
- `scan-cache.json`: every working-copy path with its mtime, size and content hash.

They put the vault's path names in clear next to `local/vault_key`, which already is; a reader of that folder has
the key. Registered as **TM-R41** in the threat model with a `Known_Gaps` test that proves it. Neither is trusted
beyond its source: a tree id is a content address; a scan entry is used only when size and mtime still match and the
mtime is older than two seconds; a reused tree id is checked to exist in the store. Deleting both costs one rebuild.

## 4. Not done, and why

- **`pull` of a head another clone pushed still walks the trees of that head through `Type_Safe`** (the fetch
  path; the skip applies only when nothing is new). On the newsroom vault that is a minute or two per pull with
  new commits, against hours before. The walk could stop at any tree that was already local, but an interrupted
  earlier pull can leave trees without their blobs, and the current walk is what repairs that; a pruned walk needs
  a completeness marker first. Next step if a pull with new commits is reported slow.
- **A three-way merge (`build_from_flat`) and `write_file` still build the whole tree.** They run only when two
  clones changed the same branch; the newsroom has one writer per vault.
- **`push` still walks the working tree once for `.conflict` files** before it runs the status (about 4 s here).
  Folding it into the status scan would move the check after the pending-branch registration, a server write;
  left as is.
- `Type_Safe` construction cost is the pattern behind most of this (3 ms per tree, 100 µs per entry, a guard
  object per path). The storage layer now reads trees as JSON; schemas remain the write-side contract.

## 5. Files

`sgit_ai/storage/Vault__Sub_Tree.py` (linear builder, JSON tree reads, flatten caches with folder ids,
`diff_trees`, incremental `build`), `sgit_ai/storage/Vault__Path_Guard.py` (memoised segment verdicts, `is_link`
takes a stat), `sgit_ai/core/Vault__Ignore.py` (one guard, cached folder rules), `sgit_ai/core/Vault__Sync__Base.py`
(scan cache, one `lstat` per file, conflict files from the scan), `sgit_ai/core/actions/commit/Vault__Sync__Commit.py`,
`sgit_ai/core/actions/merge/Vault__Merge.py`, `sgit_ai/objects/Vault__Inspector.py` (log by diff),
`sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py` (the skip), `sgit_ai/core/actions/pull/Vault__Sync__Pull.py`
(pull lists its commits again). Tests under `tests/unit/storage/test_Vault__Sub_Tree__Flatten_Fast.py`,
`test_Vault__Sub_Tree__Incremental_Build.py`, `tests/unit/sync/test_Vault__Sync__Scan_Cache.py`,
`tests/unit/workflow/pull/test_Pull__Skips_Walk_When_Head_Accepted.py`, `tests/security` TM-R41.
