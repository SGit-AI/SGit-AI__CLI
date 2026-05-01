# Debrief 01: Sparse Clone and On-Demand Fetch

**Commits:** `bc10167`, `543aa6d`  
**Date:** April 20, 2026  
**Files changed:** `Vault__Sync.py`, `CLI__Vault.py`, `CLI__Main.py`, tests

---

## Problem

A full `sgit clone` downloads every blob in a vault. For vaults with 300+ MB of content this caused timeout and memory exhaustion inside Claude Web sessions, which have a ~30s execution budget per operation. The entire vault had to be downloaded before any inspection could happen.

---

## Design

Sparse clone separates the vault into two tiers:

**Structure tier** (always downloaded):
- Branch index, branch refs, commit chain, tree objects
- All metadata needed to understand vault layout and history
- Total size: typically <1 MB even for large vaults

**Content tier** (fetched on demand):
- Blob objects — the actual encrypted file content
- Fetched lazily when a file is first `cat`-ed or `fetch`-ed

The distinction maps cleanly onto the object ID naming: `obj-cas-imm-*` objects are blobs or trees. The clone knows which are blobs from the tree entries (`blob_id` fields); it skips those during sparse clone.

---

## Implementation

### `Vault__Sync.clone()` / `_clone_with_keys()`

A `sparse: bool = False` parameter was added. Phases 5–7 of the clone pipeline (blob downloads) were extracted into `_clone_download_blobs()`. When `sparse=True`, that helper is skipped entirely.

Sparse state is written to `.sg_vault/local/clone_mode.json`:
```json
{"mode": "sparse"}
```

Full clone writes `{"mode": "full"}` for consistency.

### `sgit ls [path]`

Lists all vault files using `flatten()` (tree walk, no blob downloads). Each entry shows a status indicator:
- `✓` — blob exists in local object store (available offline)
- `·` — blob only on server (sparse / not yet fetched)

Flag extensions added in the same sprint:
- `--ids` — adds a `blob_id` column (12-char hash)
- `--json` — outputs a JSON array with full entry metadata

### `sgit fetch [path]`

Downloads and writes specific files from the server. Accepts:
- A single path (`sgit fetch docs/report.pdf`)
- A directory prefix (`sgit fetch docs/` — fetches all files under `docs/`)
- No argument — fetches the entire content tier (equivalent to completing a sparse clone)

Implementation: resolves the path in the current HEAD tree via `flatten()`, then calls `obj_store.load_from_api()` for each missing blob, writes to disk, and reports bytes downloaded.

### `sgit cat <path>`

Decrypts and prints file content to stdout without writing to the working directory. If the blob isn't in the local object store, it's fetched on demand from the API in a single `batch_read` call.

Extensions from Apr 27 surgical editing sprint:
- `--id` — prints only the blob_id (no blob download needed; from tree metadata)
- `--json` — outputs `{path, blob_id, size, content_type, fetched}` as JSON

### Sparse Pull

`sgit pull` with a sparse clone respects the sparse mode: commits and trees are fetched as normal, but the final checkout only writes blobs that are already locally cached. Files not yet fetched remain `·` in `ls` output. The `--full` flag on pull forces blob downloads for everything.

---

## Status File: `.sg_vault/local/clone_mode.json`

```
{
  "mode": "sparse"          # or "full"
}
```

Read by `Vault__Storage.load_clone_mode()` (returns `{'mode':'full'}` if absent, for backward compat with older clones).

---

## User-Facing Output Example

```
$ sgit clone --sparse vault://coral-equal-1234 ./my-vault
  ▸ Fetching branch index...
  ▸ Walking commit graph: 12 commits
  ▸ Downloading structure objects [████████████████████] 847/847
  ✓ Sparse clone complete (structure only, 0 blobs)

$ sgit ls
  · docs/architecture.pdf      obj-cas-imm-3a9f2b
  ✓ src/main.py                obj-cas-imm-8c1d40
  · README.md                  obj-cas-imm-f72e88

$ sgit cat README.md
  ▸ Fetching 1 blob...
# My Project
...
```

---

## Trade-offs

**Sparse clone is ideal for:**
- Agents inspecting vault contents (find a file, read it)
- Vaults with many large blobs where only a few are needed
- Environments with low storage quotas

**Full clone is better for:**
- Working copies where files need to be edited locally
- Offline use cases
- Performance when all files will be accessed anyway (avoids per-file RTT)
