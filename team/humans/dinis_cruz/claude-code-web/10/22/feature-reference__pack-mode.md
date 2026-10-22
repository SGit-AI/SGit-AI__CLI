# Pack mode — feature reference for 0.24.0

**For:** the sgit.ai team writing the release notes and the feature documentation. **Status:** released in sgit-ai 0.24.0 (branch merged to dev on 22 Oct 2026). **Sources:** the spec (`../10/21/spec__pack-mode.md`), the measurements (`../10/21/note__pack-mode-round-trip.md`), the tester's page (`../10/21/howto__test-pack-mode.md`), the four verification rounds (`../10/21/response__pack-mode-verification*.md`), the CHANGELOG entry under 0.24.0. This page is the one-stop summary; everything in it is tested or measured.

## 1. What it is, in one paragraph

A pack vault is a vault whose objects travel and are stored on the host as zips instead of one file per object. Every `sgit push` uploads one zip of the commit's new objects; the first push and `sgit pack compact` upload one snapshot of the whole history; a clone takes the newest snapshot plus the commit packs it lacks, in a handful of requests whatever the history's size. Files are compressed before they are encrypted, so the host holds about half the bytes for text-heavy vaults. Nothing changes on the server: the same batch, presigned, list and delete routes. Pack vaults are opt-in, created with `sgit init --packs`, and are a separate vault from any existing one.

## 2. Why

On the comms vault (1,229 commits, 33k objects, 527 MB loose) a full clone over the API took 3½ minutes because it is 700 batch reads; agents' command timeouts are shorter than that. The same history as a pack vault clones in 25 s, of which 18 s is one 251 MB download in four requests. A pull that is N pushes behind is two listings and one batch of N zips.

## 3. Commands

| Command | What it does |
|---|---|
| `sgit init --packs [dir]`, `sgit create --packs <name>` | A new pack vault: branch-index features `packs` and `blob-deflate`, `min_client` 0.24.0. |
| `sgit push` / `sgit pull` / `sgit clone` / `sgit status` | Unchanged for the user; on a pack vault they move packs. Clone takes the snapshot for the branch head (then older ones until the history is complete) and every commit pack; pull takes the commit packs it has not absorbed; push uploads one commit pack per new commit, oldest first, then the ref under compare-and-swap exactly as before. |
| `sgit pack import <normal clone> <new dir>` | Rewrites the clone's HEAD history into a NEW pack vault with its own key (blobs re-encrypted and deflated, trees deterministic, commits re-signed by the new clone's key with messages and timestamps kept). The source is untouched. The new vault's first `sgit push` uploads one snapshot. `--no-deflate` keeps blobs uncompressed; `--json` prints the stats. |
| `sgit pack export <pack clone> <new dir>` | The reverse: a NEW normal vault, nothing deflated, nothing packed. Round trip tested end to end. |
| `sgit pack compact [dir] [--dry-run]` | One snapshot of the current head; the commit packs it absorbs, the snapshots it supersedes and orphan commit packs older than a day move to `bare/packs/archive/` (copy, verify by listing, then delete the original; nothing is ever deleted without its copy; `archive/` is never deleted by the client). Refuses a clone that has not pulled, a dirty working tree, a read-only clone. |
| `sgit pack ls`, `sgit pack stats`, `sgit pack verify` | The three folders as the host lists them (packs this clone absorbed marked `*`); packs and bytes on the host plus the local compression ratio; every member of every pack checked against its content address. |

Flags on `pack` take the usual network options (`--base-url`, `--token`, `--remote`, `--transport`).

## 4. Host layout

```
bare/packs/commits/   <epoch>__<commit id>__<bytes>.zip   one per push
bare/packs/snapshots/ <epoch>__<commit id>__<bytes>.zip   first push and each compaction
bare/packs/archive/   the same names, moved by compaction; never deleted by the client
bare/refs/, bare/indexes/, bare/keys/                      exactly as on a normal vault
bare/data/                                                 empty, except tag objects (tiny, read by id)
```

A pack is a deterministic zip (ZIP_STORED, members sorted, fixed timestamps) of members named `bare/data/<object id>`: the same commit always gives the same bytes, so a pack can be rebuilt from any clone that holds the objects. The local store stays loose: packs are extracted on arrival, so every local command (`history log`, `cat`, `diff`, `branch`, `stash`, `tag`) is unchanged.

## 5. Compression

Feature `blob-deflate`: a blob is deflated (zlib level 6) before AES-256-GCM, and kept that way only when shorter; the envelope is a 5-byte magic, the iv, then the ciphertext. Trees, commits, refs, keys and the index are never compressed (trees must stay deterministic; the index must stay readable by an old client so it can read the gate). Every client from 0.24.0 reads both envelopes by inspection. Measured: 1.58× on the comms vault's plaintext as a whole (JSON 2.8×, Markdown 2.5×, `.eml` 2×, `.jsonl` 8.8×, images 1×); 2.0× on its blobs after import (355 MB → 176 MB); 1.66× on the AIUC conformance vault; 3.7× on a prose-and-JSON synthetic vault.

## 6. Numbers to quote

Comms vault history (1,229 commits, 33k objects), from a cloud sandbox against dev:

| Operation | Pack vault | Loose vault |
|---|---|---|
| Full clone | 25 s (18 s download, 4 requests) | 3½ min |
| Pull, one commit behind | 27 s (the merge walk; transfer ~2 s) | similar |
| Pull after a compaction, head already held | 1.7 s | — |
| Push of one commit | 27 s (the status/merge walks, same as loose) | — |
| Compaction (251 MB snapshot) | 76 s | — |
| Import / export (local) | 90 s / 82 s | — |

AIUC conformance vault (17 commits, 699 files, 2,087 objects; the reviewer's medians): clone 8.1 s against 28.6 s (3.5×), first push 11.8 s against 27.3 s, push of one file 5.8 s against 10.5 s, pull 3 behind 4.2 s against 4.8 s, blobs 128.6 MB against 213 MB. The safety checks added in the review rounds cost nothing measurable.

## 7. Compatibility and the gate

- A pack vault's branch index carries `min_client = 0.24.0`. A client before 0.24.0 refuses it by name ("this vault needs sgit-ai >= 0.24.0 and this is 0.23.0"); verified live against the released 0.23.0 from PyPI. Clients before 0.18.1 do not read `min_client` at all and would see an empty store (that was already so).
- A pre-release build (a branch install reporting an older number) passes the gate only because it carries the feature that set it; an unknown feature in the index voids that.
- No web view: the browser does not read packs. Anything that must be browsable stays in a normal vault, or comes back through `sgit pack export`.
- `sgit clone` (full, `--path`, `--depth`, read-only) and `clone-headless` work on a pack vault; `--path` and `--depth` take the packs whole in this version. `clone-branch` and `clone-range` refuse with a sentence.
- Tags work; tag objects are the one thing still written loose.
- A clone that was behind when a compaction ran pulls the whole snapshot on its next pull, not the packs it lacked (archived packs are never read by a pull). Compact when the team is quiet.

## 8. Security model (threat model rows TM-F37, TM-R38, TM-R39, TM-R40)

- Every pack member is verified against its content address before it is written, as a loose object is; a member is read only when its directory entry names `bare/data/obj-cas-imm-<hex>`, is stored uncompressed and declares no more bytes than the pack holds, so a zip bomb or a planted ref is refused by its entry, never inflated or written; a pack naming a member twice is refused whole; a pack whose length disagrees with its name is refused before it is opened. A forged pack cannot move HEAD: the ref still travels under compare-and-swap.
- The host learns, from pack names and zip directories, when each push happened, which commit it carried and the sizes of its objects (TM-R38, by design: the listing is the index). With `blob-deflate` it also learns how compressible each file is (TM-R40, accepted; `--no-deflate` exists).
- Compaction judges reachability from every ref the host lists; a ref it cannot read suspends orphan archiving; the head is re-read before the upload and before the moves; an aborted compaction leaves its snapshot (clones choose by the branch head, never by name); two compactions of one head both succeed (TM-R39).

## 9. Tests

`tests/unit/pack/` (unit, sync, round trip, performance gates, the review file with one test per finding across four rounds), `tests/unit/cli/test_CLI__Pack.py`, `tests/unit/crypto/test_Vault__Crypto__Deflate.py`, `tests/unit/network/api/test_Vault__API__Read_Large_Ranges.py`, `tests/security/test_Security__Fixed__Pack_Members.py`, Known_Gaps TM-R38/TM-R40. The performance gates are on request counts and bytes (deterministic), not wall time.
