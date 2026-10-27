# Architecture: the pack as the store, and the indexes it carries

**Status:** exploration, 26 Oct 2026, from the brief after the 0.25.0 field report ("ship the indexes in the zip,
assemble them locally, don't extract the files"). Nothing here is built; section 9 says what to build first.
**Builds on:** `review__indexes-and-caches-across-the-board.md` (same folder), pack mode (0.24.0), the local
caches (0.25.0), the cache layer (contract 08/12).

## 0. The idea, and why it works now when it did not in August

The August objection to indexes was right twice over: an index is one more file per thing indexed, on a host
where every file is a request; and an index that describes mutable state has to be maintained, which is more
requests, by every writer, racing. The cache layer (08/12) survived that by being per path, derived, optional
and repairable, and it stayed small.

A pack changes both terms. A pack is immutable: one zip per push, named by its commit, never rewritten, replaced
only by compaction. Anything derived from the objects in it is as immutable as the pack and can travel inside
it: no extra request, no maintenance, no race, written once by the one client that already holds the answer
(the pusher) and read by everyone who downloads the pack anyway. The index is not a file on the host that
someone keeps current; it is a member of a thing that is never current, only complete.

And the second half of the brief follows from the first: if the pack carries what a reader needs to know
*about* its objects, the reader does not need to take the objects *out* of it. The pack can be the store.

Two numbers from this week say why that matters. A clone of the synthetic vault writes 305,230 objects
(1.2 GB) into `bare/data/` and then 228,000 working files: 216 to 288 s here, and on a cloud session's disk the
curator's first command afterwards waited 17 minutes on that disk. Nearly every one of those object writes is
a copy of bytes the clone already holds, contiguously, in the one file it downloaded.

## 1. What is authoritative, what is derived, what the host may see

The design rests on the distinction sgit has kept since the start:

| | Authoritative | Derived |
|---|---|---|
| what | blobs, trees, commits (`obj-cas-imm-*`, content-addressed), refs, the branch index, keys | everything computable from those plus a key: flat maps, folder ids, diffs, graph shortcuts, the scan state, object locations |
| may be lost? | no | yes: rebuilt from the authoritative set; the rebuild is the only cost |
| trusted? | by content address (blobs, trees), by signature (commits), by CAS (refs) | never for correctness: checked against the authoritative object it claims to describe, or used only to plan |

Everything in this document is in the right-hand column, with one rule added: **a derived object may decide
what to fetch, what to open and what to write, but nothing is written to the working copy or to the store
unless the authoritative object it came from verified.** That is already how packs work (a member is verified
by its content address before it is written); the same rule carries over when the member is read in place.

What the host may see does not change. It already sees: pack names (epoch, commit id, bytes), each pack's
central directory (object ids and ciphertext sizes), the commit graph's shape through pack names, and every
ref. It never sees a path name, a file's content, a message, or which object is a tree. An index member must
keep that boundary: **ids and sizes may be clear; names, paths and relations between named things are
encrypted under the read key** like a tree is. The thing "everything is a hash" buys is that the clear part of
an index can be the join key, and the encrypted part the payload.

## 2. The pack as the store

### 2.1 Today

`sync_down` downloads a pack to memory, checks each member (stored uncompressed, name is an object id, size
matches), verifies it by content address, writes it loose under `.sg_vault/bare/data/`, and discards the zip.
The local store is always loose; `bare/packs/` exists only on the host.

### 2.2 Proposed

The clone keeps the packs it downloads under `.sg_vault/bare/packs/` (the host's names), and the object store
answers a read from either place:

1. loose, `bare/data/<id>` (objects this clone made and has not pushed; anything older code wrote);
2. packed: a local **pack index** maps `<id> -> (pack file, offset, length)`; a read is one `seek` and one
   `read` of `length` bytes (members are `ZIP_STORED`, so the bytes in the file are the ciphertext itself;
   blob deflate is inside the ciphertext, not the zip).

The pack index is derived from the zip central directories (one pass per pack when it arrives, ~1 ms per
thousand members), kept as a local file, and losable: a missing or corrupt index is rebuilt by re-reading the
central directories of the packs on disk.

Verification moves from write time to the first read of each object: the bytes read from the pack are hashed
against the id before they are used, and the verdict is remembered (a bit per object in the pack index). The
first clone of a 305k-object vault no longer hashes 305k objects before anyone can work; it hashes what it
reads, and `sgit check fsck` hashes everything.

What changes for each writer of the store:

- **push** already builds the commit pack from the loose objects of the pushed commits; after a successful push
  it keeps that pack locally and may drop the loose copies (or keep both until the next compaction; loose
  wins on a read, so correctness does not depend on the choice).
- **compaction** already replaces commit packs with a snapshot on the host; locally it does the same: a
  snapshot that arrives supersedes the packs it absorbed, which are removed once the new index covers them.
- **`vault move`**, `pack import/export`, `history` edits and `uninit`'s backup read through the same store
  API and need nothing new.
- the **three invariants** of the pack layer stand: a member is only ever `bare/data/<object id>`, stored,
  unique, and refused whole on any violation; nothing in a pack is trusted before its content address checks.

Working-copy extraction becomes a streaming read: for each entry of the head's flat map, read the blob's bytes
from the pack at its offset, decrypt, write the file, seed the scan cache. The 305k object writes disappear;
the 228k file writes remain (they are the working copy).

### 2.3 Costs and risks

- One open file handle per pack during a command (a handful; compaction keeps it a handful).
- A pack on a cloud disk is one large file: a partial download must be detected (size from the listing name,
  and the zip end-of-central-directory) before it is indexed; today's "verify before write" becomes "verify
  before index".
- Windows: a pack held open cannot be replaced; compaction's local swap must close handles first (the same
  rule `vault move` follows for `.sg_vault`).
- Zip64 for packs over 4 GB: the writer already sets `allowZip64`; the reader must index 64-bit offsets.
- A loose object and a packed one with the same id are the same bytes by definition; `fsck` reports a
  disagreement as corruption of whichever fails its hash.

## 3. What a pack carries besides objects

Each member below is one file inside the zip, under a reserved prefix (`bare/index/`), encrypted under the
read key with AES-GCM like a tree, and named by the authoritative object it describes, so it is immutable and
needs no version of its own. Readers that predate the feature refuse the pack (section 7).

| Member | Describes | Content (plaintext, before encryption) | Written by | Used for |
|---|---|---|---|---|
| **`flat/<tree id>`** | one head | every path with blob id, size, content hash, content type; every folder path with its tree id | the pusher, from its flat cache | the clone's and pull's fetch plan; the first flatten; a keyed reader's "where is this file" |
| **`diff/<commit id>`** | one commit | added, modified, deleted paths with old and new blob ids | the pusher (it computed it to build the pack) | `history log`, `pull`'s commit lines, "what did this pass change", the merge's apply map |
| **`graph/<commit id>`** | one commit | parents, timestamp, tree id, author key id, and the commit's generation number | the pusher | ancestry walks without opening commits; an exact `base..head` and merge base for any clock |
| **`manifest`** (clear) | the pack | the member ids and sizes | the zip's own central directory, already present | the pack index; nothing new to write |

Sizes on the newsroom's vault: the flat index of a 79,465-file head is ~12 MB as compact JSON, ~2 MB
deflated; a diff is proportional to the pass (hundreds of KB); a graph entry is bytes. Against a 1.22 GB
snapshot and 164 to 228 MB commit packs, the indexes are noise, and they go through the same batch write.

**Signature.** The flat and diff members are signed by the pusher's clone key over (the id they describe,
sha256 of the plaintext), as a commit is signed, and accepted on the same policy as the commit that names their
tree. Without that, a write-key holder could ship a map that disagrees with the trees and bypass the signature
the trees enjoy through their commit. With it, the index has exactly the standing of the commit, and a reader
that does not trust unsigned commits does not trust unsigned indexes either.

**Not carried.** Scan state (this machine's inodes and mtimes) and object presence (this clone's store) are
local by nature. Application indexes (what a newsroom builds over its sources) are ordinary vault content.

## 4. The local assembly: from members to a database

A pack delivers the indexes as members; the clone **assembles** them into whatever local form answers its
questions fastest. This is the load, extract, transform, save step, done once per pack, locally, where it is
cheap, by the one process that just downloaded the pack.

The natural target is SQLite (in the standard library, transactional, one file), as the local materialisation
of the pack indexes; a graph store over the commit graph is the same data with a different index. Either way,
the assembled database is a **cache with a well-known shape**, under `.sg_vault/local/`, losable, and rebuilt
from the packs on disk.

| Table | Rows | Fed by | Answers |
|---|---|---|---|
| `objects(id, pack, offset, length, verified)` | one per member | every pack's central directory | "where are the bytes of X"; fsck |
| `flat(tree, path, blob, size, hash, type)` | one per file per head kept (the newest two heads) | `flat/<tree>` | status, commit's incremental build, cat, fetch, "which file is where" |
| `folders(tree, path, child_tree)` | one per folder per head kept | `flat/<tree>` | the incremental build's reuse; the fetch plan (which folders changed) |
| `commits(id, parent, ts, tree, generation)` | one per commit | `graph/<commit>` | log, pull's list, merge base, rewind guard |
| `changes(commit, path, kind, old_blob, new_blob)` | one per changed path per commit | `diff/<commit>` | `history log --stat`, "what did this pass change", blame-like queries |
| `scan(path, mtime, ctime, size, ino, dev, hash)` | one per working file | the scan (local) | status without reading |

With this, the commands the newsroom runs every wake are a stat pass plus SQL: `status` is `scan` against
`flat` for the head; `commit` is the incremental build with reuse decided from `folders`; `pull` of N packs is
N index loads plus a diff-sized set of file writes; `history log` is a query; "where is this file" is a row
lookup and one seek into a pack.

**What stays plaintext locally.** Path names, sizes, hashes, messages: the same set the 0.25.0 caches hold
(TM-R41), in the same folder as `vault_key`. Under the sealed-vault-keys design this database must be either
encrypted at rest (SQLCipher, or the file encrypted under a key derived from the read key and opened to a
memory database per command) or memory-only, assembled from the packs on each run; the second is slower but
needs nothing new. Decide when sealed keys land.

## 5. Why the files need not be extracted

With sections 2 to 4 in place, "extract" means two different things, and only one is still needed:

- the **store** need never be extracted: the object store reads members in place;
- the **working copy** is extracted only because that is what a working copy is: files on disk for the user's
  tools. A clone that is only read (a research reader, a Lambda, SG/Vault, a pipeline that feeds its own
  database) can skip it entirely and read blobs through the index: `sgit cat` and `sgit fetch <path>` become
  one row lookup and one seek, no working copy at all. That is the "bare" clone with an index, and it is the
  shape most agents in the newsroom actually need between passes.

And a reader without any clone: the flat index of the head is one object, the pack's central directory tells
where each blob sits, and `fetch_presigned_range` already exists. "Give me this file from this vault" is one
read of the index member and one ranged read of the member's bytes, from the host, no clone, no walk. That is
the cache layer's one-request read generalised to every path of a pack vault.

## 6. What the brief says, checked against this

- *"Already provide the indexes in the zip."* Yes: section 3; one encryption and one member per index at push.
- *"Assembled locally, high performance, local databases."* Yes: section 4; SQLite first, a graph store on the
  same rows when a question needs it.
- *"Because we can encrypt the data again, this scales."* Yes, with the boundary of section 1: ids and sizes
  in clear, names and relations encrypted on the host; locally, whatever the sealed-keys decision says.
- *"Rearrange the files locally so you know exactly what you are consuming."* That is the pack index and the
  `objects` table: the clone knows, per object, which pack holds it and whether it verified.
- *"I would not even need to extract the files."* The store: never. The working copy: only for a working clone;
  a reading agent needs none (section 5).
- *"Everything is a hash, so some values can be clear."* The join keys can be clear everywhere, including on
  the host, because they are content addresses that already appear in pack directories; what must stay
  encrypted is what relates a key to a name.

One thing the brief does not say and this design must: the index is a plan, never a proof. A member read from
a pack is still verified by its address before it is used; a signed index that disagrees with its tree is the
signer's fault and is refused like a bad commit; an unsigned index on a vault that requires signatures is
ignored and the walk happens. Lose every index and nothing is lost; trust an index and nothing is written
unverified.

## 7. Format, compatibility, rollout

- Two features in the branch index, each with its min client, gated exactly like `packs` and `blob-deflate`
  (`FEATURE_MIN_CLIENT`, `gate_this_build_carries`): `pack-index` (packs carry `bare/index/*` members) and
  `pack-store` (clones may keep packs in place). A 0.24.x or 0.25.0 client refuses a pack with an index member
  whole (the member rule), so `pack-index` is a gate, not a hint. `pack-store` is local-only behaviour and
  gates nothing on the host; it is a feature so that a vault can say "its clones are expected to hold packs".
- Compaction writes the snapshot's `flat/<head tree>` and the graph members for every commit it absorbs; that
  is how an existing pack vault gains indexes without a re-push: one `sgit pack compact` by an upgraded client.
- `pack import` (loose to pack) writes them too; `pack export` ignores them.
- The local database is versioned by a schema number in its one metadata row; a mismatch drops and rebuilds.

## 8. Risks and open questions

1. **Reading through packs on slow disks** trades many small writes for seeks into one large file. On a
   cloud session's scratch disk that is the right trade (sequential download, random reads of what is used);
   measure it on the newsroom's session before making `pack-store` the default.
2. **The flat index duplicates what the trees say.** By design, like every index; the signature and the root
   check keep it honest, and `fsck --indexes` can compare a flat member to its trees in full.
3. **How much to keep in SQLite versus JSON files.** The 0.25.0 caches are JSON and they are enough for the
   per-head questions; the database pays off when questions cross heads and commits (log, blame, "what changed
   since"). Start with JSON members in the pack and SQLite as the local assembly; the members' format does not
   change if the local form does.
4. **Memory-only versus on-disk database under sealed keys.** Deferred to that design; nothing here forecloses
   either.
5. **Generation numbers** in `graph/` make `base..head` exact for any clock; the day-window walk on the branch
   is the interim.

## 9. Order of work

| Phase | What | Removes | Size |
|---|---|---|---|
| 1 | `pack-store`: packs kept locally, pack index, object store reads in place, verify-on-first-read, streaming extraction, fsck over packs, compaction's local swap | the 305k object writes of a clone; the disk wait behind the first command | 3 days |
| 2 | `pack-index`: `flat/<tree>` and `graph/<commit>` members written at push and compaction, signed; the fetch plan from two flat maps; the first flatten from the member | the last tree walks (clone, pull of an unseen head); one-request reads for keyed readers | 3 days |
| 3 | `diff/<commit>` and the local SQLite assembly (`objects`, `flat`, `folders`, `commits`, `changes`) | per-commit questions as queries; the index-only (bare) reader | 3 days |
| 4 | the remote one-request path (index member + ranged member read) in `sgit cat` / `fetch` without a clone, and in SG/Vault | the clone itself, for readers | with the SG/Vault team |

Phase 1 is self-contained and measurable on the newsroom's own session (the curator's 18 minutes is its
benchmark); phase 2 needs the gate and is where the brief's idea lands; phase 3 is where the local database
earns its keep; phase 4 is the payoff for readers.
