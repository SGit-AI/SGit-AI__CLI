# DC vault clone check — what I found, what I changed (6 Oct 2026)

**Vault:** `y8pwtjlw` (the CRM / DC collaboration vault; ~10 agents in parallel)
**Branch:** `claude/charming-babbage-5hzcxq` (on `dev` @ `2f86cf5` + the pull-guard commits)
**Ask:** "that vault is starting to not be cloned by some agents, can you check it"

## 1. Does it clone?

Yes, from this session, on both the published 0.17.0 and current `dev`, with no errors
or integrity warnings in the output. But the vault has grown ~3.5× in three days:

| | 3 Oct | 6 Oct |
|---|---|---|
| commits | 244 | 621 (first-parent chain 305 — many merges) |
| trees (unique) | 2,264 | 8,013 |
| blobs (unique, all history) | 2,919 | 9,356 |
| objects in the store (`list_files`) | — | 18,684 |
| full clone, this session | 73–90 s | **165–172 s** (commits 57 s · trees 60 s · blobs 46–50 s) |

So "not cloned by some agents" is most likely a per-command timeout in the agents'
harness (anything at 120–180 s is now crossed), not a clone error — but see §3 for a
real failure mode. **Ask the agents for the exact error text**; a timeout and a failure
look different, and the fixes below address both.

## 2. Why it got slower, and the fix — one parallel sweep instead of three dependency walks

The three clone phases are dependency walks: a commit's parents are inside its ciphertext,
a tree's children inside its. With 305 commits deep and merges, the commit phase is 300+
serial round trips before a single tree is known; the tree levels are serial too.

The server can list the whole store in one call (18,684 ids in ~11 s), and ids need no
order to download. New `Step__Clone__Bulk_Fetch` (after download-branch-meta, full clones
only): list once → fetch everything not local in 16 parallel 50-id batches, verify-before-
write as always → the existing walks run against a store that has everything (they now
skip ids that are local, and still fetch anything missing — a truncated or failed
listing only costs speed, never correctness). Sparse clones skip it.

| phase | before | after (bulk) |
|---|---|---|
| listing | — | 11 s |
| bulk fetch 18,684 objects | — | 61 s (16 workers) |
| commits walk | 57 s | 0.2 s |
| trees walk | 60 s | 12.9 s (local decrypt of 8,013 trees) |
| blobs | 46–50 s | 0.9 s |
| **wall** | **165–172 s** | **80 s** |

Also: `BATCH_READ_WORKERS` 8 → 16 (measured on the live API: ~170 → ~350 objects/s), and
HTTP 429 joins the transient set (retried with back-off) so a burst of ten agents cannot
fail a clone on a throttle. The listing includes objects unreachable from the named branch
(~4 % here) — harmless, content-addressed, ignored by fsck.

Next lever if it grows again: the 12.9 s tree phase is pure local decrypt; and the sweep is
bounded by batch throughput, so a server-side pack (one GET for a range of objects) would
be the step after this.

## 3. A real failure: `sgit clone-branch` has been broken

`sgit clone-branch` (and `clone-headless`, `clone-range`) died immediately with
`error: network or I/O failure — Name or service not known`: `CLI__Main` built a bare
`Vault__API()` with no base URL, so the request went to host `''`. Any agent that
switched to the thin clone to save time hit this. Fixed: the three commands resolve the
saved token, `--base-url` / `--remote` and `--transport` exactly as `sgit clone` does
(`_clone_family_sync`). Two tests.

## 4. The missing objects are a push bug — now 41, was 17

`sgit check fsck` on a fresh clone: **41 missing objects**, all blobs, all absent on the
server, referenced by commits from many agents across 2–6 Oct (`@drafts`, `@CRM`,
`@Security`, `@inbox`, `@abp`, merges). Every one is an **older version** of a file.

Root cause in `Vault__Sync__Push.push`: blobs to upload were `clone HEAD tree − remote
HEAD tree`. Trees of every pushed commit were uploaded, blobs only of HEAD. A file created
or changed in commit 1 and changed again in commit 2, pushed together (agents commit
several times per run), leaves commit 1's blob referenced by an uploaded tree and never
sent. Not visible to the pusher (HEAD is complete), visible to every other clone's fsck,
and it makes `history diff`/`show` of those versions fail.

Fix: `Vault__Batch.collect_chain_blob_entries` — the blobs of every commit in the push
chain (each tree decrypted once), still minus the remote HEAD's blobs. Both push paths
(normal and first push). Four two-clone tests, including "created then deleted before
push" and "no re-upload of what the remote HEAD has".

**The 41 objects already missing cannot be recovered by this fix** — they exist only in
the clones of the agents that created them, if those clones still exist. `sgit check
upload-objects` on such a clone is the recovery tool (it uploads the named local objects).
If no clone has them, those historical versions are gone; HEAD content is unaffected.

## 5. Tests and numbers

- new: `test_Step__Clone__Bulk_Fetch.py` (lists once, every object requested exactly once,
  walks fetch nothing after the sweep, no-listing fallback completes, sparse skips),
  `test_Push__All_Chain_Blobs.py` (4), 429 retry, thin-clone sync construction (2)
- adjusted: the two workflow step-list tests (+1 step), `n_blobs` counts sweep-fetched blobs
  (three profile/read-only tests asserted the count)
- `pytest tests/unit/ -n auto`: **3903 passed**
- real vault, after the fix: `sgit clone-branch` completes (91 s, 3,435 files — it still walks all 624 commits serially before HEAD, so the thin clone is now *slower* than a bulk full clone; the sweep is deliberately not applied to it because it would download every historical blob); bulk full clone `fsck` finds the same 41 missing objects as the walk-based clone and 18,684 objects on disk; working trees identical except one commit that landed between the two clones.
