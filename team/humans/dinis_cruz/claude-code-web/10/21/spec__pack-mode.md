# Spec: pack mode for sgit (CLI-only, packs-only vaults, no server change)

**Status:** proposal, 21 Oct 2026, agreed in conversation with Dinis; revised the same day after the review on cli.sgit.ai (*Pack mode, read closely*): decisions 1 to 5 taken as below; not built. **Scope:** a push,
pull and clone mode plus an import and a compaction command. Everything else in the CLI is
unchanged. **Server:** none of this needs a server change; the routes used are `batch`
(write/read), `presigned/initiate|complete|read-url`, `list`, `delete`, all present in
`sgraph-ai-app-send` 0.34.0 and exercised live on 20 Oct.

## 1. Goals and non-goals

Goals: a push costs one pack upload and the ref move; a pull costs one listing and the packs it
lacks; a clone costs the newest snapshot and the packs since it; large packs move straight to S3
by presigned URL; small ones through the API; nothing on the host is ever deleted by the mode;
every object is verified by id before it is written locally, as today.

Non-goals (this round): web app or static-reader support; reading packs in place without
extraction (version 2); mixed vaults (loose objects and packs written together); pruning.

## 2. Layout on the host

```
bare/packs/commits/   <epoch_s:010d>__<commit_id>__<bytes>.zip
bare/packs/snapshots/ <epoch_s:010d>__<commit_id>__<bytes>.zip
bare/packs/archive/   <epoch_s:010d>__<commit_id>__<bytes>.zip      (moved from commits/)
bare/refs/, bare/indexes/, bare/cache/, bare/keys/                   unchanged
bare/data/                                                            not written in pack mode
```

- `epoch_s` is the writer's clock at pack creation, in whole seconds (review decision 5: a listing
  shows the host each push's size and time; seconds order the listing as well as milliseconds and
  say less). It orders listings; nothing depends on its accuracy, and names stay unique by commit
  id. The security page gets one line when the mode ships: a host that can list sees, per push,
  the commit id, the size it added and the writer's clock to the second.
- `bytes` is the pack's size; the client chooses the route from it and checks it after fetch.
- A pack's member paths are `bare/data/<object-id>`, exactly as `publish --bundles` writes them, so
  extraction is a copy into the loose store.
- Zip rules as in `Vault__Publish__Bundles`: `ZIP_STORED`, members sorted by name, fixed
  timestamps, Zip64 allowed, deterministic bytes for the same object set.

## 2a. Blob compression before encryption (option for the pack trial)

Today blobs are encrypted uncompressed, and ciphertext does not compress (`publish --bundles`
measured DEFLATE making it larger). Compressing the plaintext *before* encryption is where the gain
is. Measured 21 Oct on the comms vault's working copy, per file (the way blobs are stored):

| | Size | Ratio | CPU (120 MB) |
|---|---|---|---|
| raw | 120.3 MB | | |
| deflate level 1 | 77.9 MB | 1.54× | 2.0 s |
| deflate level 6 | 76.0 MB | 1.58× | 2.9 s |
| deflate level 9 | 75.8 MB | 1.59× | 3.5 s |
| lzma level 6 | 70.3 MB | 1.71× | 34.6 s |

Images (53 MB of jpg and png) are the incompressible part; JSON goes 2.8×, markdown 2.5×, email 2×,
JSONL logs 8.8×. The store's history is the same kinds of file, so a 527 MB store would be roughly
330 MB. Rules if it is adopted:

- **Blobs only.** Trees and commits stay as they are: their encryption is deterministic so that
  rebuilt trees match byte for byte across clients, and a browser's deflate does not produce the
  same bytes as zlib. Blobs use a random IV, so determinism is not needed there.
- **Deflate, stdlib, level 6.** No new dependency; browsers decode it with `DecompressionStream`.
  lzma buys 8 % for 12× the CPU.
- **Keep the smaller.** Compress, compare, store whichever is shorter with a one-byte encoding
  flag in the blob envelope (a new envelope version, gated by `min_client` like 128-bit ids), so
  images and zips cost one fast pass and nothing more.
- **Interop vectors** for the browser: deflate + AES-GCM round trips byte for byte, as for every
  other primitive.
- **Threat model row.** Compress-then-encrypt lets the host see how compressible a file is, and
  an attacker who can place chosen bytes in the same file as a secret and watch the ciphertext's
  size can learn about the secret (the CRIME family). Sizes are already visible to the host;
  secrets are already refused at commit; a per-path opt-out (never compress under `inbox/`, say)
  and optional padding close the rest. Record it as an accepted gap with those mitigations.
- **Where to introduce it:** the pack trial vault is new and gated, so it is the cheap place to
  turn the new blob envelope on; the packs themselves stay `ZIP_STORED`.

## 3. The vault flag

The branch index gains `features: ['packs']` and `min_client: <first version with pack mode>` at
import. `Vault__Format` already enforces both: a client without the feature refuses the vault by
name; the web app and static readers refuse it the same way. A pack vault never writes
`bare/data/`.

## 4. Commands and behaviour

### 4.1 `sgit pack import <source-dir> --vault-key <new-key> [--base-url …]`

From a **full** clone of an existing vault (refuses on a partial clone, as `publish` does):

1. Re-encrypt the reachable history into the new key, reusing `Step__Move__Build_Temp_Vault`'s
   walk (blobs, then trees children-first, then commits parents-first, with the id map; signatures
   re-made with this clone's branch key, as `move` does).
2. Build one snapshot pack of every object reachable from the new head.
3. Create the vault on the server (as `init`), write the branch index with the flag and
   `min_client`, upload the snapshot (route by size, §6), write the ref.
4. Leave the source untouched. Repeatable: a second import makes a second vault.

### 4.2 `sgit push` in a pack vault

1. Collect the objects of every commit being pushed that the remote lacks, exactly as
   `Vault__Batch.collect_chain_blob_entries` plus the trees and commits do today.
2. Build one pack per pushed commit (several commits pushed at once = several packs, so a pack's
   name is always one commit id). Objects shared between them are put in the first.
3. Upload each pack by size (§6).
4. Move the ref with the existing compare-and-swap; the branch index as today.
5. Record each pack name in `.sg_vault/local/packs_absorbed.json`.

### 4.3 `sgit pull` and `sgit status` in a pack vault

1. `list bare/packs/commits/`; diff against `packs_absorbed.json`.
2. Fetch the missing packs: those under the threshold in batch reads of up to 50, those over it
   by presigned URL, 16 in flight as today.
3. For each pack: verify size, open, verify every member's id against its bytes
   (`extract_verified`), write into the loose store. A member whose id does not match is refused
   and reported per object, as fetch failures are today; the pack is not recorded as absorbed.
4. Record the pack names. Then the ref and the merge as today.
5. Status needs the ref and the index only, as today; it does not list packs.

### 4.4 `sgit clone` of a pack vault

1. Read the index; see the flag; refuse if the client is too old.
2. `list bare/packs/snapshots/`; take the last name (epoch order). Fetch it (§6; for a large
   snapshot, parallel `Range` reads of 10 MB each). Verify and extract.
3. `list bare/packs/commits/`; fetch and extract all of them.
4. Walk commits and trees locally to confirm the head is complete (the existing walk steps, which
   now find everything on disk); fetch any object still missing through the ordinary read route
   as a safety net, never as the normal path.
5. Record every pack name as absorbed; check out as today.

Scoped and shallow clones: version 1 takes the snapshot whole and keeps the scope for checkout
and later pushes. That is a step back in bytes for the agents' daily `--path <folder> --depth 1`
clone (3 MB and 13 s on the loose comms vault against the whole 430 MB snapshot; review decision
3), so: agents' working vaults stay loose until version 2, the trial measures it (run 5 in §10),
and version 2 reads the snapshot's central directory by `Range` (2.7 MB for 34k members, measured)
and then only the needed members, one `Range` each, 16 in flight. The seekable-HTTP reader that
does this is about twenty lines and was exercised on 20 Oct.

### 4.5 `sgit pack compact [--when]`

Trigger (checked on push, run on demand or by a scheduled job): `commits/` holds more than
`PACK_COMPACT_COUNT` packs (default 50, to be tuned) or their total size exceeds
`PACK_COMPACT_RATIO` (default 0.10) of the newest snapshot.

1. Build the snapshot of every object reachable from the current remote head.
2. Upload to `snapshots/`.
3. Read it back: `read-url` + `Range` of the tail to read the central directory; check the member
   set equals the expected id set. Abort on any difference, leaving everything as it was.
4. For each commit pack absorbed (every pack whose commit is reachable from the snapshot's commit):
   upload the same bytes to `archive/` with the same name, then `delete` it from `commits/`.
5. Also move to `archive/` every pack in `commits/` whose commit is unreachable from the head and
   whose epoch is older than `PACK_ORPHAN_AGE` (default one day): the pack an agent session left
   behind when its ref move lost the race and the session ended (review decision 4). Nothing is
   deleted; clones stop fetching it.
6. Old snapshots stay. Nothing else is deleted.

The move needs no download: a pack's bytes are a deterministic function of its commit (the objects
that commit introduced, sorted, fixed timestamps, as `Vault__Publish__Bundles` already builds them),
so the compacting clone rebuilds each pack from its loose store, checks the size against the name,
and uploads that to `archive/` (review note 1). A rebuilt pack whose size differs from the name is
downloaded instead and reported.

Idempotent and crash-safe: a pack present in both `commits/` and `archive/` is removed from
`commits/` on the next run after the archive copy is verified by size.

### 4.6 `sgit pack ls` / `sgit pack verify`

`ls`: the three folders with sizes and dates. `verify`: fetch the newest snapshot's directory by
`Range` and confirm the union of snapshot + `commits/` covers every object reachable from the
head (ids only, no members downloaded).

## 5. Local layout

```
.sg_vault/bare/data/              extracted objects (version 1 reads from here, unchanged code)
.sg_vault/packs/                  fetched packs kept as files (optional cache; version 2 reads by offset)
.sg_vault/local/packs_absorbed.json   names of packs whose objects are in the loose store
```

## 6. Route selection

| Pack size | Upload | Download |
|---|---|---|
| ≤ `LARGE_BLOB_THRESHOLD` (4 MB) | batch write | batch read (up to 50 packs per request) |
| > 4 MB | `presigned/initiate` + part PUTs + `complete` | `presigned/read-url` + GET, or parallel `Range` GETs |
| host without presigned (disk, memory, `serve`) | batch write (no Lambda limit there) | batch read |
| static host / folder | n/a (read-only) | plain GET |

The fallback `presigned_unavailable` is reused unchanged.

## 7. Listing when the host cannot list

A static host has no listing: `publish` writes the three folders' names into the manifest. The
local disk server answered a listing with zero objects on 16 Oct (in the SG/Send brief); until
fixed, a client on such a host falls back to the commit walk for `commits/` discovery (each pack
holds its commit, so the walk finds pack names by commit id), which is slow and correct.

## 8. Failure handling

- A pack that fails size or id verification is not absorbed and is reported; the pull continues
  with the others and the ref is not moved past what is complete, as today.
- A push whose pack upload succeeds but whose ref CAS fails leaves an orphan pack in `commits/`;
  the next push from that clone reuses it (same commit id, same bytes) and `compact` ignores
  packs whose commit is unreachable from the head (they stay, harmless, until a prune exists).
- Two writers: the ref CAS serialises them; packs never collide (names are commit ids).

## 9. Tests

Unit (in-memory API): push writes one pack per commit and nothing under `bare/data/`; pull lists
once and fetches only missing packs; a corrupt member is refused per object; clone from
snapshot + commits equals a loose clone object for object; compact verifies before moving and
moves before deleting; a crash between archive upload and delete is tidied; the flag refuses an
old client and the web-style loose reader. Integration (real server, 3.12 venv): the presigned
path for a pack over 4 MB; `Range` reads of a snapshot's directory. Live: the comms vault import
and the four performance runs in the article.

## 10. Performance runs

1. Cold clone of the imported comms vault: pack mode vs API batches; from the sandbox and from a
   laptop.
2. 100 one-file pushes: seconds and requests per push, both modes.
3. Pull after 10, 100, 1,000 pushes without compaction, then after; set the defaults in §4.5.
4. Two writers pushing concurrently for a minute: no lost packs, ref always consistent.
5. A scoped shallow clone (`--path security --depth 1`) of the pack vault against today's 13 s and
   3 MB on the loose vault, to size the version-2 work.

## 11. Later (not this round)

Reading packs by offset without extraction; scoped reads of a snapshot by `Range`; web app and
static reader support; in-place migration of an existing vault (`vault format --feature packs`
plus one snapshot, loose objects left as the archive); prune; the SG/Send `append` route for
growing a snapshot in place instead of rewriting it (the 20 Oct brief, parked; review decisions 1
and 2).
