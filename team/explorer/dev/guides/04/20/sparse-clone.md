# Sparse Clone — On-Demand File Access

## Problem

Large vaults (300 MB+, hundreds of files) fail or time out when cloned inside
Claude Web. The full clone workflow downloads every blob before the working copy
is usable, which exceeds Claude's network/memory budget for a single session.

## Solution

Sparse clone downloads only the **structure** — branch index, refs, all commits,
all tree objects — but skips blob content entirely. The working directory starts
empty (just `.sg_vault/`). File content is fetched on demand, one file or
directory at a time.

This mirrors the web UI's "load list first, fetch content on click" pattern.

---

## Workflow

### 1. Sparse clone (structure only, no file content)

```bash
sgit clone --sparse <vault-key> [directory]
```

- Downloads: branch index, refs, all commits, all tree objects
- Skips: all blob objects (file content)
- Working directory: empty (just `.sg_vault/`)
- Config: `sparse: true` written to `.sg_vault/local/config.json`
- Speed: proportional to commit history depth, not vault size

### 2. List what's in the vault

```bash
sgit ls                   # list all files
sgit ls docs/             # list files under docs/
```

Output:
```
  ✓     4.2K  README.md
  ·  1024.0K  data/large-export.json
  ·     8.1K  src/main.py
  ·     2.3K  src/utils.py

  1/4 file(s) fetched locally
  · = remote only  (run: sgit fetch <path>  to download)
```

`✓` = blob in local object store (file can be read)  
`·` = blob on server only (needs `sgit fetch` first)

Works on both sparse and full clones.

### 3. Fetch a file or directory on demand

```bash
sgit fetch README.md      # fetch one file → writes to working copy
sgit fetch src/           # fetch all files under src/
sgit fetch                # fetch everything (converts sparse → full clone)
```

- Already-cached blobs skip the download and just write to disk
- Large blobs (>2 MB) use presigned S3 URLs automatically
- Returns count of fetched vs already-local files

### 4. Read a file without writing to disk

```bash
sgit cat README.md        # decrypt and print to stdout
sgit cat src/main.py | head -20
```

- Fetches from server if blob not yet cached (and caches it for next time)
- Never writes a working-copy file — stdout only
- Works on all vaults (sparse and full)

---

## Comparison

| | Full clone | Sparse clone |
|---|---|---|
| Download size | All blobs | Structure only |
| Working directory | All files present | Empty until fetched |
| `sgit status` | Normal | Unfetched files invisible |
| `sgit fetch` | No-op (all local) | Downloads specific file(s) |
| `sgit cat` | Works | Works (fetches on demand) |
| `sgit push` | Normal | Normal |
| `sgit commit` | Normal | Only commits fetched files |

---

## Implementation Notes

- `Vault__Sync.clone(sparse=True)` skips phases 5-7 of `_clone_with_keys`
  (blob download and working copy extraction); blob download extracted to
  `_clone_download_blobs()` helper
- `Vault__Sync.sparse_ls()` — flattens HEAD tree, checks `obj_store.exists(blob_id)` per entry
- `Vault__Sync.sparse_fetch()` — downloads missing blobs via `batch_read` (small)
  or presigned S3 (large), then writes to working copy
- `Vault__Sync.sparse_cat()` — fetches blob if absent, decrypts, returns bytes (no disk write)
- `Vault__Sync.status()` — in sparse mode, filters `deleted` list to only blobs that
  are locally present (unfetched files are invisible, not reported as deleted)
- `_get_head_flat_map()` — shared setup helper used by all three sparse methods

---

## Known Gaps / Next Steps

1. **`sgit fetch --dry-run`** — show what would be downloaded without fetching.

2. **`sgit ls --json`** — JSON output for scripting and agent tooling.
