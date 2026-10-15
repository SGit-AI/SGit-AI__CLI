# Response to "sgit issues found on 14 October 2026", and the comms-vault performance report

**Date:** 14 Oct 2026. **Code:** `dev` at 5e85205 plus the fixes on `claude/charming-babbage-5hzcxq`.
**Vault used:** the comms / DC collaboration vault (`y8pwtjlw` on `dev.send.sgraph.ai`), read-only:
cloned, measured, nothing pushed.

## The comms vault today

| | 6 Oct | 14 Oct |
|---|---|---|
| Objects in the store | 18,720 | **35,423** |
| Commits | 626 | 1,227 |
| Trees | — | 16,391 |
| Blobs | 9,404 | 16,315 |
| Files in the working copy | — | 5,101 |
| On disk after a full clone | 173 MB | 527 MB |

Listing the store takes 21 s on its own. It is a different vault from a week ago.

## What was sequential, and what was not

**A full `sgit clone` was not the slow path.** With 0.21.0's code it took about 3½ minutes for
35,423 objects: the listing (21 s), the bulk sweep (about 140 s, 50 objects per request, 16
requests in flight), then a local tree walk (33 s of decrypting 16,391 trees), 47 late blobs
(1.3 s) and the checkout (3.6 s). The progress bar moves in steps of 50, which is the batch
size.

**`sgit pull` was.** Everything that goes through the pull path (`pull`, `fetch`, `status`'s
chain fetch, `widen`) had two sequential loops:

1. **One request per commit.** The commit walk fetches wave by wave, each wave being the
   previous wave's parents, so a linear history of N new commits is N round trips before a
   single tree arrives. On the comms vault that is 1,227 requests.
2. **One request per blob.** After the graph walk, blobs were fetched with `api.read()` one at
   a time, inside a loop. 16,315 requests.

Measured on the live vault, fetching the whole head into an empty store (the worst case of a
pull far behind), unmodified 0.21.0 code against the fix:

| | Before (0.21.0) | After |
|---|---|---|
| Commit and tree walk | 189 s | included below |
| Blobs | 5.4 per second: 818 in 150 s, so about 50 min for 16,315 | included below |
| **Whole fetch** | **about 53 minutes** (projected from the capped run) | **186 s** |
| Objects fetched | — | 35,423, every one verified before it was written |

An agent that is a day behind on this vault is behind by hundreds of commits and thousands of
blobs. That is what they were reporting.

### The fix

- **Blobs go through the batch route** (`_fetch_missing_objects`, pass 2): 50 per request, 16
  requests in flight, with per-object verification and per-file failure classification kept.
  Blobs flagged large go through `read_large` four at a time.
- **Far behind, the walk sweeps.** After 25 sequential commit fetches, a whole-vault clone lists
  the store once and fetches everything missing in bulk, the way a clone does; the walk then
  finds its objects on disk. The "new commits" list and counts still cover what the sweep
  brought. Partial clones (scoped or shallow) never sweep: they must not hold what they do not
  track, and a host that cannot list leaves the walk to finish as before.
- Tests: `tests/unit/sync/test_Pull__Batched_Blob_Download.py` (no single-file reads, chunked
  requests, the bar moves per chunk, a lost blob is classified absent, a corrupt one is refused)
  and `tests/unit/sync/test_Pull__Far_Behind_Sweep.py` (lists once and fetches in bulk, a short
  pull never lists, a partial clone never sweeps, a host that cannot list still completes).

## The four reported issues

| # | Issue | Side | Status |
|---|---|---|---|
| 1 | Disk mode: every append-lane write scans the whole store | **server** | Confirmed from the server code: `Storage_FS__Local_Disk.folder__files__all` iterates the entire store and filters by prefix; `append()` calls it on every write for the 1,000-entry cap. In the brief to the SG/Send team. |
| 2 | Files over 4 MB cannot be pushed to, or fetched on demand from, a server without S3 | client | **Fixed.** `presigned initiate` / `read-url` answer `400 S3 storage mode required` on memory and disk servers. Push now falls back to the batch; clone, pull, `fetch` and `cat` fall back to the read route (`Vault__API.read_large`). A 401/403/5xx still surfaces. Reproduced and proven on the real in-memory server with a 4.25 MB file: `tests/integration/test_Large_Blob__No_S3__Integration.py` fails on 0.21.0 at the push, passes now (push, full clone, sparse fetch). |
| 3 | `clone-headless` then `fetch` always fails | client | **Fixed.** A headless clone holds keys and config only; `fetch`, `ls` and `cat` now bring the tracked head down first (index, ref, commits and trees, never blobs), the way `clone --sparse` does. `tests/unit/sync/test_Sparse__Headless_Fetch.py`. Note: on a vault with a long linear history that first fetch walks the commits one request each, as `clone --sparse` does; the sweep is for whole-vault clones only. |
| 4 | Concurrent full clones queue on one server process | **server** | Deployment note: the Docker entry point runs one uvicorn worker. In the brief. |

The smaller observations in the report (access token on every route including append writes,
caps holding under concurrency, refusals correct) need nothing from the CLI.

## Verification

| Check | Result |
|---|---|
| Unit | 4232 passed |
| Security | passed |
| Bandit (baseline) | clean |
| Integration, large blob on the real in-memory server | passed (fails on 0.21.0) |
| Live comms vault | full clone 3½ min; pull-path fetch of the whole head 186 s (was ~53 min) |

## Files

- Fixes: `sgit_ai/core/actions/pull/Vault__Sync__Pull.py`, `sgit_ai/network/api/Vault__API.py`,
  `sgit_ai/core/actions/push/Vault__Batch.py`, `sgit_ai/core/actions/clone/Vault__Sync__Clone.py`,
  `sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py`.
- Brief to the SG/Send team (issues 1 and 4, the large-file note, and the MCP removal):
  `brief__to-sg-send-team__disk-mode-performance-large-files-mcp.md` in this folder.
