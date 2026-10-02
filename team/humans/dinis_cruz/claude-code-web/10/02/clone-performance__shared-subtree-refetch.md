# Clone performance — the tree walk re-fetched shared sub-trees once per parent

**Date:** 2026-10-02
**Branch:** `claude/charming-babbage-5hzcxq` (from `dev` @ `0c9be4b`, v0.16.3)
**Vault probed:** `y8pwtjlw` (the DC collaboration vault, 172 commits at the time of the run)
**Reported with:** sgit-ai v0.14.27, stuck at `▸ Walking trees: obj-cas-imm-4c9e63979601`

## 1. What the clone was doing

An instrumented run of the real clone steps (derive keys → index → branch meta → walk
commits → walk trees) against the live vault, with the BFS tree walk mirrored exactly and
every batch request timed:

| phase            | time   | requests | notes                                                       |
|------------------|--------|----------|-------------------------------------------------------------|
| walk commits     | 32 s   | ~100     | linear chain: one commit per round trip                     |
| walk trees       | 377 s  | 205      | 10,098 tree ids requested for **2,236 unique** trees        |
| (blobs, not run) | ~15 s  | ~52      | 2,563 small blobs, fetched 8 chunks in parallel             |

The per-level picture of the tree walk is the whole story:

| level | queue | unique | duplication | requests | download |
|-------|-------|--------|-------------|----------|----------|
| 1     | 170   | 170    | 1.0×        | 4        | 7 s      |
| 2     | 2263  | 269    | **8.4×**    | 46       | 86 s     |
| 3     | 1938  | 508    | 3.8×        | 39       | 73 s     |
| 4     | 3561  | 811    | 4.4×        | 72       | 132 s    |
| 5     | 2135  | 460    | 4.6×        | 43       | 75 s     |
| 6     | 31    | 18     | 1.7×        | 1        | 1 s      |

Two defects compound:

1. **`Vault__Graph_Walk.walk_trees` queued a shared sub-tree once per parent.** `next_q`
   was only guarded by `sub not in visited`, and `visited` is updated at *processing* time,
   so within a level every root tree that pointed at the same unchanged folder enqueued
   its own copy. A 170-commit history whose root trees share most of their folders made
   the next level ~8× larger than it needed to be, and all of those duplicates went to
   `on_batch_missing` and so to the server. Nothing was written twice (the per-tree
   `visited` guard still held), but 4.5× the bytes and requests went over the wire.
2. **`Vault__API.batch_read` fetched its 50-id chunks one after another.** Each Lambda
   round trip costs ~1.7 s for 50 objects, so a 3,561-id level became 72 serial requests
   (132 s) during which the only progress line is the last *decrypted* tree id — which is
   why it looked hung on `obj-cas-imm-4c9e63979601`. The blob download step already fanned
   out 8 chunks in parallel; the tree walk did not.

The commit walk is a third, smaller cost: a linear chain needs one round trip per
commit because the parent id is inside the ciphertext. ~0.19 s per request × 172.

## 2. The fix (this branch)

- `Vault__Graph_Walk.walk_trees` keeps a `seen` set (queued ∪ visited) so every tree id is
  enqueued — and requested — exactly once. `on_batch_missing` still gets one call per BFS
  level. Pull's tree walk uses the same class and benefits identically.
- `Vault__API.batch_read` fans its chunks out over a bounded pool (`BATCH_READ_WORKERS = 8`,
  matching the blob fan-out); each chunk keeps its own 502 → per-file → presigned-S3
  fallback, and the first chunk failure still propagates as before. Single-chunk calls stay
  inline. `Vault__API__Static` already did this; `Vault__API__In_Memory` is unaffected.
- `Step__Clone__Walk_Trees` / `__Head_Only` emit `Walking trees: fetching N tree(s)` before
  each level's download so a large level is visible instead of looking stuck.

Measured on the same vault after the change, full `sgit clone`:

| phase    | before (probe)     | after        |
|----------|--------------------|--------------|
| commits  | 32 s               | 32 s         |
| trees    | 377 s              | **24 s**     |
| blobs    | ~15 s              | 14 s         |
| checkout | –                  | 0.4 s        |
| **wall** | **~7–8 min**       | **73 s**     |

`sgit check fsck` on the result reports 17 missing objects — all blobs, all also absent
on the server (`not_found` on a direct read), referenced by trees in commits
`7b72ec534ca6`, `3cd27e9b3222`, `ff4cc8df75e8`, `81c7fd7c6cb4`, `68797954d2ef` (several are
`*.conflict` files and `baseline.json`). That is a push from some client that never
uploaded those blobs; it is pre-existing and unrelated to the walker (the old walker's
probe store lacks them too). Worth noting: the blob step prints `2586 blobs` and does
not say that 17 came back empty — see §4.

Tests: 3 new walker tests (shared sub-tree requested once across 100 roots, duplicate
roots, one call per level) and 4 new `batch_read` tests (chunking + all returned, single
chunk inline, chunk failure propagates, 502 fallback confined to the failing chunk).
`pytest tests/unit/ -n auto` → **3841 passed**.

## 3. Would the newer releases have helped?

No. PyPI's latest is **0.16.0** (published 2026-08-20 from the last `dev → main` merge);
`dev` is at v0.16.3 but nothing after 0.16.0 has reached PyPI because publishing runs on
`main` only (`ci-pipeline__main.yml` sets `should_publish_pypi: true`; the dev pipeline
had publishing removed on 2026-08-14). Between 0.14.27 and today the walk code changed
once — the verify-before-write hook on 2026-08-20 — which does not touch the algorithm.
`Vault__Graph_Walk` itself was last edited 2026-05-11. So 0.16.0 clones this vault exactly
as slowly as 0.14.27; the fix needs a release that includes this branch.

The one `dev`-only change that *is* relevant to the follow-up question is `sgit vault
move` rewriting object ids (2026-08-20/21), which is also not on PyPI.

## 4. Follow-ups (not done here)

- **Commit walk round trips.** 172 serial requests at ~0.19 s. `curl` timing shows ~0.11 s
  of each ~0.43 s request is the TLS handshake (a reused connection answers in 0.16 s).
  `urllib.request.urlopen` opens a fresh connection per call; a per-thread persistent
  `http.client.HTTPSConnection` in `Vault__API._request` would roughly halve the commit
  walk and shave the tree/blob phases too. Needs care with proxies (`HTTPS_PROXY` is
  honoured by urllib today) and the retry path.
- **Silent missing blobs on clone.** `_download_blobs_by_id` drops `None` payloads
  without a word; the clone reports success and only `fsck` reveals the gap. A one-line
  `warning` with the count (and the first few file names, which the tree entries give)
  would have told the user about the 17 absent blobs at clone time.
- **`sgit check fsck` has the same per-commit re-walk**: it reported `44256 trees` for a
  vault with 2,264 unique trees because it restarts the tree walk from each commit with a
  fresh `visited_trees`. Local disk only, so it is seconds not minutes, but it scales
  with commits × tree size.
- **Full-clone shortcut**: a non-sparse clone downloads every reachable object anyway, so
  `list_files('bare/data/')` + one parallel bulk fetch + a local walk would collapse all
  three phases into one fan-out. It changes semantics (unreachable objects would be
  fetched too), so it is a design decision, not a patch.

## 5. Rekey while keeping history — where things stand

The brief's todo: *"a rekey loses the entire commit history"*. That is true of
`sgit vault rekey` (the `wipe` → `init` → `commit` flow: it deletes `.sg_vault/` and starts
a fresh history from the working tree). It is **not** true of `sgit vault move` on `dev`:

- `Step__Move__Build_Temp_Vault._rewrite_object_graph` classifies every object by
  reachability from the refs, then re-encrypts bottom-up — blobs, then trees with their
  `blob_id`/`tree_id` remapped and names re-encrypted deterministically, then commits with
  `tree_id` and `parents` remapped — storing each at its recomputed content address.
  Unreachable objects are carried too. Refs and the branch index are re-pointed.
- Verified locally on a throwaway vault (`init` + 3 commits): after the rewrite the new
  store under the new read key resolves the clone ref to a 4-commit chain
  (`commit 3 → commit 2 → commit 1 → init`) with the right file names at each step, 11
  objects in, 11 out, and **zero** shared ids between old and new store. Only the
  local build step was run (no access token in this session, so push/verify/delete-source
  were not exercised against the server).

So "rekey keeping history" already exists as `sgit vault move --new-key <key>`; the
hashes change (as expected) but the chain, messages and trees all survive. What it does
*not* do, and what the user may actually want:

- **Keep the same vault id.** `move` derives a new vault id from the new key, so it is a
  fork-and-delete, not an in-place rotation. Sharing links and `.sg_vault/local` configs on
  every clone go stale. An in-place variant would need the server to accept a full
  object-set replacement under the same id (write new objects, swap refs/index, delete
  old), and the read-key → ref-id derivation (`derive_ref_file_id(read_key, vault_id)`)
  means the named ref id changes with the key even if the vault id does not.
- **Ship it.** It is on `dev` only; PyPI 0.16.0 still has the old in-place re-encrypt
  that keeps ids (and therefore produces vaults that the new strict verify refuses).
- **`sgit vault rekey` should either delegate to `move` or say plainly that it discards
  history**, since today the two commands overlap in name and differ exactly on the point
  the brief cares about.

A full-chain check of `move` against the server (push → verify → clone the new key →
`history log` shows all commits) is the next thing to run, with a token.
