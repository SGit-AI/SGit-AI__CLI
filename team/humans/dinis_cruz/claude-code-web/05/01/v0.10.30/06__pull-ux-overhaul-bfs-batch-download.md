# Debrief 06: Pull UX Overhaul and BFS Batch Tree Download

**Commits:** `35ad09a`, `0c29c72`, `1d88371`  
**Date:** April 30, 2026  
**Files changed:** `Vault__Sync.py`, `Vault__Inspector.py`, `CLI__Progress.py`

---

## Problem

### UX: 60+ seconds of silence before any feedback

`sgit pull` on a vault with 55 new files showed:

```
Pulling from named branch...
                                    ← [60-146 seconds of nothing]
Downloading objects [████] 1069/1069
Done.
```

The "1069 objects" figure was also wrong: it included commits and tree objects already fetched during the graph-walk phase, making the progress bar misleading.

### Performance: 1019 individual HTTP requests for tree objects

The root cause of the 146-second wait was `_fetch_missing_objects()` issuing one HTTP request per tree object. A 55-file vault with 5 directory levels had ~1019 tree objects across all commits. Each request had ~50ms round-trip → 50 seconds minimum, worse with retries.

### `sgit log` short ID bug

`format_commit_log()` was slicing `commit_id[:12]` to get the short hash. But object IDs have the format `obj-cas-imm-{12 hex chars}`, so `[:12]` returned the literal string `"obj-cas-imm-"` — useless as a display ID. Every commit showed `obj-cas-imm-` as its identifier.

### Diff attribution bug in `inspect_commit_chain()`

The per-commit file change counts (added/modified/deleted) were computed in a single pass comparing each commit against its child (the previous iteration's flat map). This is backwards: commit N's changes should be measured against commit N's parent, not its child. First commits appeared to contain all files; subsequent commits appeared empty.

---

## Fix 1: BFS Wave Batch Downloading (`0c29c72`)

`_fetch_missing_objects()` was rewritten to use the same BFS + batch_read pattern as `clone()`.

### Structure

```
Phase 1: BFS commit walk
  - frontier = [latest_commit_id]
  - per wave: batch_read all missing commits
  - collect root_tree_ids and commit metadata

Phase 2: BFS tree walk  
  - frontier = root_tree_ids from Phase 1
  - per depth level: batch_read all missing trees
  - globally deduplicated via seen_trees set
  - expand each tree → enqueue child tree_ids for next wave

Phase 3: collect missing blobs
  - from seen_trees in Phase 2
  - deduplicated via seen_blobs set
  - download in batch with progress bar (blobs only)
```

**Before:** 1019 individual HTTP requests  
**After:** ~5–6 batch requests (one per depth level in Phase 2)  
**Result:** graph-walk drops from ~146s to ~2-3s for a 55-file vault

### Deduplication

`seen_trees` and `seen_blobs` prevent re-processing objects that appear in multiple commits. In a long history where the same subtree exists in many commits (e.g., an unchanged `docs/` directory), it's fetched exactly once.

---

## Fix 2: Pull UX with Live Progress (`35ad09a`)

### `CLI__Progress` new phases

```python
elif phase == 'scan':
    # Overwrite same line (no newline) — shows current progress while walking
    line = f'  ▸ {message}: {detail}'
    print(f'\r{line:<79}', end='', flush=True)

elif phase == 'scan_done':
    # Commit the line with a newline
    line = f'  ▸ {message}: {detail}'
    print(f'\r{line:<79}', flush=True)

elif phase == 'commit':
    # Per-commit log line, indented with ↳
    entry = f'  ↳ {message}  {detail}'
    if len(entry) > 79: entry = entry[:76] + '...'
    print(entry, flush=True)

elif phase == 'stats':
    # Timing summary at the end
    print(f'  ⏱ {message}', flush=True)
```

### During Phase 1 (commit graph walk)

Each commit processed emits a `scan` update (overwrites same terminal line):
```
  ▸ Walking commits: 12/55
```

After all commits are collected, `scan_done` commits the line, then one `commit` line per new commit (oldest-first):
```
  ▸ Walking commits: 55 commits, 1019 trees
  ↳ 3a9f2b8e  2026-04-28  add report.pdf  [blobs:+1 trees:+3]
  ↳ 8c1d4092  2026-04-29  update config   [blobs:+2 trees:+1]
```

### Progress bar (Phase 3 — blobs only)

The `detail` field of the `download` phase was changed from `"N/M"` where M = total objects (commits + trees + blobs) to just the blob count. This gives accurate progress:

```
  ▸ Downloading objects [████████████░░░░░░░░] 34/55
```

### Timing Stats

`_fetch_missing_objects()` returns a stats dict:
```python
{'t_graph': 2.1, 't_download': 4.3, 'n_commits': 12, 'n_trees': 847, 'n_blobs': 55}
```

`pull()` measures checkout time separately, then emits:
```
  ⏱ graph-walk 2.1s  blobs 4.3s  checkout 0.8s  (12 commits, 55 blobs)
```

### Final Pull Output (after all fixes)

```
Pulling from main...
  ▸ Walking commits: 12 commits, 847 trees
  ↳ 3a9f2b8  2026-04-28  add architecture docs     [blobs:+12 trees:+5]
  ↳ 8c1d409  2026-04-29  update config files        [blobs:+3  trees:+2]
  ↳ f72e883  2026-04-30  fix typos in README        [blobs:+1  trees:+1]
  ▸ Downloading objects [████████████████████] 55/55
  ⏱ graph-walk 2.1s  blobs 4.3s  checkout 0.8s  (12 commits, 55 blobs)
Done.
```

---

## Fix 3: Commit Short ID and Diff Attribution (`1d88371`)

### Short ID fix

```python
# Before (wrong — slices off the prefix, returns it):
short = commit_id[:12]   # → "obj-cas-imm-"

# After (correct — skips the prefix):
short = commit_id[12:]   # → "3a9f2b8e1c4d"
```

Applied in two places: `_fetch_missing_objects` commit_infos and `format_commit_log` oneline mode.

### Two-pass diff attribution in `inspect_commit_chain()`

```python
# Pass 1: collect all flat maps (newest → oldest)
raw = []
for commit_id in chain:
    flat = sub_tree.flatten(commit.tree_id, read_key)
    raw.append({'commit_id': commit_id, 'message': ..., 'flat': flat})

# Pass 2: diff each commit against raw[i+1] (its parent)
for i, entry in enumerate(raw):
    flat        = entry.pop('flat')
    parent_flat = raw[i + 1]['flat'] if i + 1 < len(raw) else {}
    
    added    = sum(1 for p in flat if p not in parent_flat)
    deleted  = sum(1 for p in parent_flat if p not in flat)
    modified = sum(1 for p in flat if p in parent_flat and
                   flat[p].get('blob_id') != parent_flat[p].get('blob_id'))
    
    new_blobs = added + modified
    new_trees = len(_dir_set(flat) - _dir_set(parent_flat))
    
    entry.update(added=added, modified=modified, deleted=deleted,
                 new_blobs=new_blobs, new_trees=new_trees, total_files=len(flat))
```

The `_dir_set()` helper computes the set of unique directory paths implied by a flat map — used to count how many new tree objects a commit requires.

### `sgit log` defaults to `--oneline`

`cmd_log()` was changed to default to oneline mode unless `--graph` is explicitly requested, since the full multi-line format was verbose for normal use.
