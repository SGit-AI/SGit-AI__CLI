# Pack mode: the round trip, built and measured

**Date:** 21 Oct 2026. **Branch:** `claude/charming-babbage-5hzcxq` (for 0.24.0). **Spec:** `spec__pack-mode.md` (same folder). **Article:** `article-draft__a-pack-per-push.md`.

This note records what was built for pack mode, how the round trip normal vault → pack vault → normal vault is tested on disk, and the numbers: the synthetic gates that run in CI, and the live trial on dev with the comms vault's history.

## 1. What a pack vault is, in one paragraph

A pack vault (branch-index features `packs` + `blob-deflate`, `min_client` = the creating client) keeps no loose objects on the host. Each push uploads one deterministic zip of the commit's new objects to `bare/packs/commits/<epoch>__<commit>__<bytes>.zip`; the first push and `sgit pack compact` upload one snapshot of everything reachable from the head to `bare/packs/snapshots/`. A clone lists the two folders, takes the newest snapshot and every commit pack it has not absorbed, and extracts them into its ordinary loose store, member by member, each verified against its content address before it is written. A pull does the same for commit packs only; a clone whose commit packs were compacted away takes the snapshot. Refs, the branch index and keys travel exactly as before, so push's compare-and-swap, the rewind guard, signatures and the format gate are unchanged. Blobs are deflated before encryption (envelope v2, kept only when shorter). No server change.

## 2. What was built

| Piece | Where |
|---|---|
| Blob envelope v2 (`DEFLATE_MAGIC + iv + GCM(deflate(plaintext))`), read by inspection | `crypto/Vault__Crypto.py` (`encrypt(..., deflate=True)` at the one blob call site; refs, index, keys, commits, trees never deflated) |
| Features `packs`, `blob-deflate`; `init --packs` sets them and `min_client` | `storage/Vault__Format.py`, `core/Vault__Sync.py` |
| Packs: names, deterministic zips, verified extraction, listing, absorbed record, `sync_down`, `push_packs`, `push_snapshot` | `core/actions/pack/Vault__Packs.py` |
| Hooks: push (packs instead of Phase A/B objects; first push = snapshot), pull and status (sync packs before the walk), clone (`Step__Clone__Bulk_Fetch.pack_vault_fetch`) | `core/actions/push/Vault__Sync__Push.py`, `pull/Vault__Sync__Pull.py`, `status/Vault__Sync__Status.py`, `workflow/clone/Step__Clone__Bulk_Fetch.py` |
| Import / export (the round trip) | `core/actions/pack/Vault__Pack_Convert.py` |
| Compact, ls, verify, stats | `core/actions/pack/Vault__Pack_Maintain.py` |
| CLI: `sgit pack import|export|compact|ls|verify|stats`, `sgit init --packs`, `sgit create --packs` | `cli/CLI__Pack.py`, `cli/CLI__Main.py` |
| Parallel ranged presigned downloads (`read_large`): 8 × 8 MB in flight | `network/api/Vault__API.py` |

Where the build differs from the spec: `sync_down` always reconciles the newest snapshot (a clone that already holds its head commit records it as absorbed without a download; one whose commit packs were archived takes it whole), so compaction can never strand a clone; the partial-clone flags (`--path`, `--depth`) take the packs whole in this version, as the spec allows for v1; compaction verifies a copy by the host's listing (name + size) and rebuilds the pack from the loose store when every object is local (byte-identical, by determinism) rather than reading 400 MB back.

## 3. The round trip, as tested on disk

`tests/unit/pack/test_Pack_Convert__Round_Trip.py` builds a normal vault with four commits (adds, an edit, a binary file, a delete), pushes it, then:

1. `pack import` → a new pack vault (new key). Asserted: identical working copy; the same commits with the same messages and timestamps, every one re-signed by the new clone's key and verifying; every object id the content address of its bytes; the source store byte-identical before and after; `status` says N ahead, nothing pushed.
2. `push` → one snapshot on the host, no `bare/data/` object. `clone` → identical working copy and history.
3. `pack export` from the clone → a new normal vault (new key). Asserted: identical working copy and history, no v2 blob in its store, no `packs` feature; `push` → loose objects only; `clone` → identical.
4. The three vaults share no host file.

`test_Pack_Vault__Sync.py` covers the pack vault in use: first push, clone in three requests without ever asking for a loose object, push from a clone as one commit pack, status says behind, three pushes pulled in one batch read, two clones converging, delete and edit in a pack, branch-only push, a blob over the batch budget, compaction (refuses a stale clone, dry run changes nothing, snapshot + archive, archived bytes identical to the originals, idempotent, a fresh clone takes only the snapshot, a clone left behind by compaction pulls through the snapshot, a clone holding the head records the snapshot without a download, orphans archived only when older than a day), verify on a tampered pack, nothing unverified written by a clone of a tampered pack, the gate refusing an old client. `test_Vault__Packs.py` covers names, determinism, extraction, listing, fetch grouping. `tests/security/test_Security__Fixed__Pack_Members.py` is the attack set (TM-F37); `Known_Gaps` has TM-R38 and TM-R40.

## 4. Synthetic gates (`tests/unit/pack/test_Pack__Performance_Gate.py`)

A vault of 20 commits, each adding a folder of 10 prose-like 2 KB files (200 files, 262 objects), built loose and packed on the counted in-memory host. Requests are deterministic, so these are hard gates; wall time is recorded, not asserted.

| Operation | Loose vault | Pack vault | Gate |
|---|---|---|---|
| Host bytes | 532 KB | 189 KB (2.8×) | pack < 70 % of loose; every prose blob deflated; blob ratio ≥ 2 (measured 16×) |
| Clone | 9 requests (grows with the store: ≥ objects/50) | 5 requests (index, meta, two listings, one batch) | pack ≤ 8 and < loose |
| Pull, 5 pushes behind | 11 requests | 7 (two listings, one batch of 5 packs, the ref reads) | pack ≤ 8, one batch carrying all 5, < loose |
| Push of one commit | 45 requests | 14 | pack ≤ loose + 2; no `bare/data/` write |

The clone and pull gates are the point: a pack clone is the same five requests at 20 commits and at 1,227, where the loose clone is 700 batch reads.

## 5. Live trial on dev: the comms vault's history as a pack vault

Source: the full clone of the comms vault (1,227 commits, 16,391 trees, 16,268 blobs, 35,423 objects, 527 MB loose). Everything below ran from the cloud sandbox (the same place as the earlier measurements: 3½ min for a full loose clone over the API).

**Import** (`sgit pack import`, local, no network): 137 s. Blobs 355.4 MB → 176.2 MB of ciphertext (2.02×; 15,841 of 16,268 deflated, the rest incompressible); the store on disk 526 MB → 322 MB. 47 references the source itself could not resolve (older file versions never uploaded by the agents that made them, the known gap from the 10/06 check) are carried unchanged, so those historical files stay missing exactly as in the source. Snapshot of the head: 33,141 objects, 251 MB, built in 4 s once the reachable set is known (46 s for the 1,227-commit walk, trees memoised).

All numbers are one run each, wall clock, from the sandbox (`user` CPU in brackets where it is most of the time). The loose figures are the earlier measurements on the same vault from the same place.

| Step | Pack vault (dev) | Loose vault, for comparison |
|---|---|---|
| `sgit push` (first push: one 251 MB snapshot, 24 multipart parts) | 67 s (46 s of it the reachable-set walk, 4 s the zip, the rest upload) | the loose first push of this history was never measured from here; its object count alone is 35,423 writes |
| `sgit clone` (full history, 33,094 objects, 251 MB) | **58 s**: packs fetched in 18.0 s / 4 requests (~14 MB/s with 8 ranges in flight), 33 s the clone's tree walk, 3 s checkout. After the head-only walk for pack clones (same session): **25 s** (18.6 s download, 1.0 s trees, 3.2 s checkout) | **3½ min** over the API (bulk-fetch, 16 batches in flight); 110 s static local; 69 s local API |
| `sgit push` of one commit from the clone (one file: an 8.9 KB commit pack) | 38 s, then 27 s after the pack path stopped running the loose path's flatten/collect walks (22 s CPU remain in the pull-first status and merge code, the same on a loose vault) | — |
| `sgit pull` of that one commit pack (two listings, one batch) | 27 s (22 s CPU: the merge's tree flatten, as on a loose vault; the transfer itself is ~2 s) | a pull one commit behind on the loose vault: 13 s for a scoped `--depth 1` clone's worth; whole-vault pulls were 180–206 s when far behind |
| `sgit status` | 4 s | — |
| `sgit pack compact --dry-run` | 6 s | — |
| `sgit pack compact` (new snapshot 251 MB, 2 commit packs + the old snapshot to `archive/`) | 76 s | — |
| `sgit clone` after compaction (one snapshot, 33,102 objects) | **25 s** | 3½ min |
| `sgit pull` on a clone that already held the head, after compaction (snapshot recorded, not downloaded) | 1.7 s | — |
| `sgit pack ls` / `pack stats` | 1.6 s / 52 s (stats decrypts every blob to measure the ratio; 863 s before the walk was memoised) | — |
| `sgit pack export` (local: 1,229 commits, 15,603 trees, 16,270 blobs re-encrypted v1) | 82 s; working copy identical to the pack clone; `check fsck` reports exactly the 47 objects missing in the source | — |
| `sgit pack import` (local) | 90 s (137 s on the first run while the machine was also running the test suite) | — |

Host after the trial: `snapshots/` 1 pack 251.1 MB, `commits/` 0, `archive/` 3 packs 251.1 MB, loose objects 0. Local store: 33,103 objects; 16,270 blobs on the branch, 15,843 deflated; 354.9 MB plaintext → 176.2 MB stored (2.01×). The host holds 251 MB for a history whose loose store was 527 MB.

What the trial says: the transfer is solved (18 s for the whole history, four requests; a pull is one batch), and the remaining seconds in `push`, `pull` and the first `clone` are CPU in walks the loose path also does — the clone's full-history tree walk (33 s, now skipped for pack clones), the merge's flatten and the status check (22 s per push or pull on this vault). Those are the next targets and they are independent of pack mode.

Throwaway vaults created for the trial were deleted on dev afterwards (`sgit vault delete-on-remote`); the comms vault itself was never written to.

## 6. For the email team's trial

- Needs the 0.24.0 release (`sgit update`), then `sgit init --packs` (or `sgit create --packs`) for the new vault; `sgit pack ls` / `stats` / `verify` to look at the host; `sgit pack compact` when `commits/` grows past ~50 packs or a tenth of the snapshot (the thresholds in `Vault__Packs`).
- No web view: a pack vault's objects are inside zips the browser does not read. Anything that must be browsable stays in a normal vault, or comes back through `sgit pack export`.
- Older clients are refused by name (`min_client`), not confused by an empty store.
