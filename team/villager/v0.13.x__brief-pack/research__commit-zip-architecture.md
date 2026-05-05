# Research — Commit-Zip Architecture

**Date:** 2026-05-05
**Status:** Architecture agreed, not yet scheduled for implementation. Ships at the END of v0.13.x once all other work is done. Visualisation v07 (projection analysis) ships earlier as the validation tool.
**Predecessors:** Dinis's voice-memo brief (v0.27.4 — "Commit Object Bundling for Performance Optimisation") + Opus refinement (this doc).

---

## What this is

An optimisation layer **on top of** the existing SGit architecture: per-commit ZIP files that bundle just the objects newly created by that commit. Pure client-side construction, no backend changes, fully backward-compatible.

**The architecture is identical to today's vault model.** A vault is still a chain of commits referencing trees referencing blobs. The commit zip is *just a delivery mechanism* — it's literally a zip file on the server with the encrypted objects inside, named by commit-id.

---

## Locked decisions (Dinis 2026-05-05)

| # | Decision |
|---|---|
| 1 | **Delta mode.** Each commit's zip contains ONLY objects newly created by that commit (commit obj + new tree objs + new blob objs). NOT the cumulative ancestor closure. |
| 2 | **Inclusion rule:** "first-introduced by this commit." If commit N references an object created at commit N-3, that object is in commit N-3's zip, not N's. |
| 3 | **Additive storage** on the server: individual `bare/data/<id>` objects PLUS commit zips at `bare/commits/<commit-id>.zip`. Storage cost ~2×. Acceptable. |
| 4 | **Sequencing: ship LAST in v0.13.x** — capstone optimisation after B01–B08 + visualisation v01–v06 have landed. |
| 5 | **Naming:** `bare/commits/<commit-id>.zip` on the server. ZIP_STORED (no compression — encrypted bytes are high-entropy). |
| 6 | **100% compatible with current sgit architecture** — pure optimisation layer. Not a new data model. |
| 7 | **Local `bare/` looks identical regardless of clone path** — same per-object layout after the zip is extracted. The zip is a transient delivery file, discarded post-clone. |
| 8 | **Visualisation-first dev approach** — a projection tool ships before the implementation, showing exactly what each vault would gain. See visualisation brief v07. |

---

## Architecture

### Server storage (post-this-feature)

```
bare/
├── data/<object-id>          existing — individual encrypted objects
├── refs/<branch-id>          existing
├── indexes/<index-id>        existing
└── commits/<commit-id>.zip   NEW — per-commit content bundle
                              ZIP_STORED; contains only objects newly
                              created by this commit
```

The `data/` and `commits/` paths coexist. Old clients see `commits/` and ignore it. New clients prefer `commits/` and fall back to `data/` on 404.

### Push flow (per commit)

1. Standard encrypt → produces N new objects (1 commit + a few new trees + new blobs).
2. **Existing path:** upload each new object to `bare/data/<id>` (kept for backward-compat + as the random-access fallback).
3. **NEW path:** assemble a ZIP_STORED archive containing those same N objects (filenames = object-ids, contents = the encrypted bytes), upload to `bare/commits/<commit-id>.zip`.
4. Push state file tracks which commits are zipped (so resumable push handles partial-zip-upload state).

### Clone flow

1. Fetch branch index + named-branch ref (existing — small).
2. **Walk commit chain** by fetching commit objects via existing `bare/data/<commit-id>` (commits are tiny; ~50 commits = single batch_read call).
3. For each commit in the chain, fetch `bare/commits/<commit-id>.zip` — **in parallel**, typically 8–16 concurrent. On 404 for any one zip, fall back to per-object fetch for that commit's objects.
4. Extract each zip into local `bare/data/` (deduplicated by object-id; same object appearing in two zips is an error condition but harmless — both have the same content).
5. Standard checkout: walk HEAD's tree, decrypt blobs, write working copy. **Unchanged from today.**

### Local layout (post-clone)

```
.sg_vault/
└── bare/
    ├── data/<object-id>      decrypted-on-demand encrypted blobs
    ├── refs/<branch-id>      branch heads
    └── indexes/<index-id>    branch index
```

**No `bare/commits/` directory locally** — zips are extracted then discarded. Repeated clones of the same vault land in the exact same on-disk shape regardless of whether they used commit-zip or per-object fetch.

### Zip file format

- **ZIP_STORED (no compression).** Encrypted objects are high-entropy; DEFLATE yields ~0% reduction at meaningful CPU cost. STORED is byte-pass-through.
- **Filenames inside the zip = object-ids** (e.g., `obj-cas-imm-aabb1122ccdd`).
- **Contents inside the zip = the encrypted bytes** (no envelope, no manifest, no metadata).
- **Reading a zip** is O(1) per file via the central directory; no decompression cost.
- **osbot-utils zip support** likely covers the read path; if not, `zipfile` from stdlib is sufficient (no new dependency).
- **Per-file overhead** ~30 bytes (local header) + ~22 bytes (central directory entry). For a 10-object zip: ~500 bytes overhead. Negligible.

### Backward compat

- Old clients fetch `bare/data/<id>` per-object; they never look at `commits/`. Continue to work identically.
- New clients on an old server: try `bare/commits/<commit-id>.zip`; on 404, fall back to per-object fetch. Transparent degradation.
- Old vaults migrating to new clients: nothing to migrate. Server can lazy-build commit zips if/when a new client requests one (or skip and use per-object always — also fine).
- New vaults: always have commit zips. Both paths work.

---

## Why this lives in the workflow framework

Per-commit zip operations are natural workflow steps:

**On push** (`Workflow__Push`):
- Existing steps unchanged.
- New step: `Step__Push__Build_And_Upload_Commit_Zip` runs after the per-object upload step. Reads the new objects from local `bare/data/`, zips them, uploads to `bare/commits/<commit-id>.zip`.

**On clone** (`Workflow__Clone`):
- New step: `Step__Clone__Download_Commit_Zips` replaces the existing `Step__Clone__Walk_Trees` + `Step__Clone__Download_Blobs` steps when commit zips are available. After the commit-walk step, this new step parallel-fetches all needed zips and extracts.
- Fallback: if `Step__Clone__Download_Commit_Zips` returns "no zips found" (404 on first probe), the existing tree-walk + blob-download steps run instead.

This means commit-zips slot into the workflow framework as **a single step swap**, with the rest of the pipeline unchanged. Clean.

---

## Performance projection

Case-study vault (42 commits, ~300 unique trees post-HMAC-IV migration, 165 blobs):

| Metric | Today (post-B02 + B05) | With commit zips |
|---|---:|---:|
| Clone HTTPs | ~5 (BFS waves) | ~50 (1 per commit, parallel) |
| Server S3 GETs per HTTP | ~100–200 | 1 |
| Total server S3 GETs | ~500–800 | ~50 |
| Round-trip latency cost | ~250ms | ~400ms (8 in-flight) |
| Clone wall-clock | ~10–15s | ~3–5s |

The win is **server-side per-object S3 GET reduction** (the actual H4 from the B07 diagnosis). Total bytes transferred is identical; what changes is how the server fetches them from S3.

Storage cost on server: **~2× the per-object total**. ~10 MB vault → ~20 MB. Acceptable.

---

## Visualisation-first dev approach

Per Dinis's suggestion: **build the projection analysis BEFORE the implementation.**

A new visualisation `sgit show commit-zip-projection <vault-dir>` that, for any local vault, computes:
- Commit chain length + per-commit object counts.
- Hypothetical commit-zip sizes (sum of object sizes per commit).
- Hypothetical clone HTTP profile vs current.
- Projected speedup.

Output: a side-by-side dashboard "today vs projected." Same analytical pattern as the other visualisations.

This achieves three things:
1. **Validate the optimisation BEFORE writing it** — see if the projection numbers agree with the case-study diagnosis.
2. **Helps prioritise** — which vault shapes benefit most? Tiny vaults (already fast) won't benefit; deep-history vaults will.
3. **Becomes the measurement tool** — after implementation, run the same viz to confirm projected ≈ observed.

Captured as visualisation brief v07. Ships in parallel with the rest of v01–v06 (after v01 framework). Implementation comes much later as an unscheduled v0.13.x late-sprint brief or an early v0.14.x item.

---

## Open questions (small)

1. **Commit zip max size.** Initial commit may include ~all blobs in the vault. For a 100MB initial commit, that's a 100MB zip. Single HTTP can handle this, but worth a sanity check on memory usage during build / extract.
2. **Concurrent push of two commits to the same branch** — not a problem (different commit-IDs → different filenames), but verify the push state file handles "two zips uploading in parallel" cleanly.
3. **Partial zip upload (push interrupted)** — same checkpoint resume pattern as existing per-object upload. Resume re-uploads the zip (small) rather than per-object.

---

## What's not in scope

- **Server-side zip building.** That was archived B08. If we ever want it, this doc's wire format (ZIP_STORED of object-ids → encrypted bytes) is what the server would build.
- **Range bundles** (one zip covering multiple commits). Not needed; per-commit incremental is the right shape for client-side construction.
- **Patches / delta encoding.** Future optimisation; out of scope for v0.13.x.
- **Bundle-only mode** (drop individual `bare/data/`). Loses random access; rejected.

---

## Status

| Item | Status |
|---|---|
| Architecture agreed | ✅ |
| Visualisation projection brief (v07) | Authored, ready (this commit) |
| Implementation brief | NOT yet authored — wait until v01–v06 + B01–B08 are landing or landed; then write the implementation brief |
| Implementation timing | Last brief in v0.13.x or first brief in v0.14.x; decision point is the projection-tool numbers |

When ready, the implementation brief will be **B09 — Commit Zip Storage** in this pack. Until then the architecture is captured here for reference.
