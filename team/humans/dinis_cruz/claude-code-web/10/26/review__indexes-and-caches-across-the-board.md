# Review: indexes and caches across sgit, after 0.25.0

**Asked (26 Oct):** the agents report big improvements on 0.25.0 but a couple of commands still take long; the
suspicion is the cache. And: the original design had *indexes* (cross-references computed once, paid once,
benefiting everyone, losable without losing data). Should they come back, as indexes or as the cache, and can the
pack distribute them? Should large vaults simply be pack vaults?

**Answer in short.** The slow commands are not the cache being slow; they are the places the cache did not yet
exist (a fresh clone's first command) and the one walk the cache cannot help with yet (a pull that brings a head
this clone has never seen). Both are on the branch: section 2. On indexes: what the design called indexes already
exists, twice, under different names, and the gap is exactly the one you describe. The thing worth adding is one
object, the **flat index of a head** (what the local flat cache holds), encrypted under the read key, signed by
its pusher, carried in the pack: section 4. Pack vaults for anything past a few thousand files: yes, section 5.

## 1. What exists today, by name

| Name | Where | What it holds | Authoritative? | Who pays, who benefits |
|---|---|---|---|---|
| **branch index** | `bare/indexes/<id>` on the host | the named branches, their ref ids, keys, format, features | **yes** (the only thing under `indexes/`) | every clone reads it; the pusher writes it |
| **cache layer** (contract 08/12, v0.15) | `bare/cache/value/*`, `bare/cache/pointer/*` on the host | per path: an encrypted copy of a hot file, or a pointer to its blob or tree, at an id derivable from the read key and the path | no: derived, repairable (`sgit cache repair`), dropped by `vault move` | the aware writer at push; a reader that wants one file in one request (SG/Vault, a Lambda) |
| **flat cache** (0.25.0) | `.sg_vault/local/flat-cache/<tree id>.json` | the head flattened: path → blob id, size, hash, type; folder → tree id | no: a pure function of the tree id (a content address) | the first command on a head; every later command on it |
| **scan cache** (0.25.0) | `.sg_vault/local/scan-cache.json` | per working-copy file: git's index key (mtime, ctime, size, inode, device) and the hash | no: rebuilt by reading the file | every scan after the first; now also seeded by every write sgit makes |
| **packs** (0.24.0) | `bare/packs/{commits,snapshots,archive}/` | the objects themselves, zipped per push, plus snapshots | yes for the objects they carry | the transport; one listing and one batch read per clone |

So "the indexes" of the 08/06 design became the cache layer: per-path, host-side, derived, never trusted for
correctness. The design principle you state held throughout: every one of these can be deleted and nothing is
lost, because the authoritative data is the immutable, content-addressed objects plus the refs and the branch
index, and everything else is a function of them and the key.

What the 08/06–08/12 design did not have, and 0.25.0 added locally, is the **whole-vault** derived data: the
flattened head and the folder ids. That is the one a 38,000-folder vault needs on every command, and the one
that is expensive to recompute (a walk of every tree: ~45 s of decrypt and parse here, 2 minutes on the
newsroom's vault at 0.24.0). The cache layer is per path by design (one request for one file) and cannot answer
"what is the whole head" without a walk.

## 2. The commands that still take long, and why

From the newsroom's field report (26 Oct, first morning on 0.25.0):

| Command | Reported | Cause | State |
|---|---|---|---|
| first `status` on a fresh 4.2 GB clone, cloud session | 18 min 23 s (1 min CPU; the rest disk) | the scan cache only knew files a scan had hashed, so the first scan read every file back from a slow disk | fixed on the branch: every write sgit makes (clone, pull, read-only pull, switch, history edits) records the file in the scan cache under the hash of the bytes it wrote; a full clone also writes the head's flat cache. First status after a clone here: 20.1 s → 8.2 s, and the 18 minutes was that read |
| first `pull` on a read-only evidence clone | 226 s | the same read (a read-only pull scans the working copy for its dirty-tree check) | same fix |
| `pull` of a whole pass, +6,807 blobs | 8 min 5 s (1 min 21 s user) | measured below: the walk of every tree of the new head through `Type_Safe` (the one walk the flat cache cannot serve, because this clone has never seen that head) plus 6,807 file writes and reads | the walk is what section 4's index removes; the writes are the disk |

Measured here (synthetic vault, a 300-file pass pushed from one clone and pulled in another, under cProfile):
566 s, of which the fetch's walk of 154,454 tree loads through `Type_Safe.from_json` was 347 s, and
`_checkout_flat_map` writing all 229,310 files of the merged tree was 171 s (612,282 `open` calls). Both are
fixed on the branch: the fetch does not open a folder of the head this clone last accepted (its record is written
only once every object of that head was local) and reads the trees it does open as JSON; the merge writes only
the files whose blob changed; the new head is flattened by copying the unchanged folders from the cached old
head. Re-measured clean (a fresh clone, then a 300-file pass pulled under cProfile): **566 s → 31.7 s**, and what is left is the dirty-tree scan (15 s, a stat pass over 228k files), the missing-blob check (6 s, `exists` over 235k ids) and pruning empty folders (5 s): the vault's size, not the pass, but seconds of it.

## 3. What is computed repeatedly, and what kind of thing each is

The question "index or cache" is answered per item by three properties: **derivable from what** (the objects and
the key, or this machine's filesystem), **sensitive to whom** (path names are plaintext metadata: never on the
host in clear), and **who can compute it cheaply** (the writer that just built it, or only a reader after a full
walk).

| Derived data | Computed by | Cost today | Derivable from | Sensitive | Cheap for |
|---|---|---|---|---|---|
| the head's flat map and folder ids | status, commit, push, pull, log, diff, cat, fetch | 1 s from cache; ~45 s to rebuild here (77k trees) | the head tree + read key | yes: every path name | the committer (it built the tree) and anyone holding the previous head's map plus the diff |
| per-commit change counts (`history log`) | log | seconds (pruned diff) | two trees + key | yes | anyone with both maps |
| base..head commit list (pull) | pull | ms per commit within a day's window | commit objects | message text, yes | anyone |
| the objects a head needs that this clone lacks (pull, clone) | pull with new commits, clone | the full tree walk through `Type_Safe`: minutes | the new head's tree walk, or its flat map | yes (the map) | the pusher: it has the map |
| scan state of the working copy | every scan | 4 s stat pass on 228k files | this machine's filesystem | local by nature (inodes, mtimes) | only this machine |
| object presence (`exists` over 228k ids) | pull's missing-blob check, push planning | ~1 s | the local store | no | this machine |
| pack listing and sizes | pack sync, compaction | one listing | the host | no (already visible) | the host |

The first and the fourth rows are the same object. Everything else is either cheap now or local by nature.

## 4. The one thing to add: the flat index of a head, in the pack

**The object.** `idx-flat-<tree id>`: the flat map of one head (paths, blob ids, sizes, hashes, content types,
folder tree ids), as JSON, deflated, encrypted under the read key with AES-GCM like a tree, and **signed by the
pusher's clone key over (tree id, sha256 of the plaintext)** exactly as a commit is signed. Its name carries the
tree id, so it is as immutable as the head it describes: no invalidation, ever; compaction keeps the current
head's and archives the rest with its pack.

**Where it travels.** In a pack vault, as one more member of the commit pack and of the snapshot:
`bare/cache/flat/idx-flat-<tree id>`. The pusher already holds the map (its flat cache: it built the tree), so
writing it is one encryption. On a loose vault the same object can go to `bare/cache/flat/` with the cache layer's
rules (aware writer, repairable, dropped on `vault move`); optional there, since loose vaults are the small ones.

**What a reader does with it.** Three things, in order of value:

1. **A pull or a clone plans its fetch from it instead of walking.** The puller holds the old head's map (its
   flat cache) and the new head's index: the folder ids that differ name exactly the trees to fetch, and the
   entries whose blob ids are new name the blobs. No tree is opened to find out what is missing. This removes the
   walk in row 4 of section 3: minutes on the newsroom's vault, every pull with new commits.
2. **It seeds the flat cache**, so the first command after a clone or a pull opens no tree (today a clone
   computes this itself after extraction, which is fine but is the 45 s).
3. **A reader without a clone gets the whole head in one object** (SG/Vault, a Lambda): with the pack's central
   directory and the ranged read that already exists, that is "which file is where" in one request and the file
   in a second. This is the per-path cache layer's promise, generalised: not one hot path, every path.

**Trust.** The host cannot forge it (AES-GCM under the read key). A write-key holder could write a wrong one,
which is the same power that holder has over trees, except that trees are bound to a signed commit and the index
is not — hence the signature: under `signatures-required` the index is accepted on the same policy as the commit
that names its tree id, and otherwise it is checked the way the local flat cache already is (the root tree's
entries must match the index's root level: one object read; blob ids are content addresses, so an entry can only
ever name authentic bytes). What an index can never do is change what a clone verifies before writing: every
object still lands through verify-then-write by its own content address. A wrong index can make a pull fetch the
wrong set (it then fails the missing-blob check, as today) or seed a wrong map (the root check catches an emptied
or substituted one; a deeper swap by a signing teammate is their signature on it). This keeps the principle: lose
every index and nothing is lost; trust an index and nothing is written unverified.

**Compatibility.** A pack member outside `bare/data/` is refused whole by 0.24.x and 0.25.0 (the zip-bomb and
duplicate-member rules), so this is a format feature: `pack-index` in the branch index's features, with its min
client, exactly how `packs` and `blob-deflate` gate today. Pack vaults are new and their agents upgrade on a
brief; the gate refuses an old client with the command that fixes it.

**Size.** The newsroom's head: 79,465 entries. As JSON with 12-hex ids and short hashes ≈ 12 MB, deflated ≈ 2 MB.
Against a 1.22 GB snapshot and 164–228 MB commit packs, noise.

**Not in it.** Scan state (this machine's inodes), object presence (this clone's store), commit graph shortcuts
(the day-window walk is already cheap; generation numbers would be a commit-schema change for a display feature).

**Effort.** Writer: the pusher serialises its flat cache, signs, encrypts, adds the member: a day. Reader:
fetch planning from two maps, the root check, the signature policy, the seed: two to three days with tests.
Gate and member rule: hours. A `Known_Gaps`/threat-model row for what an index can and cannot do.

## 5. Normal vault or pack vault

Yes to the split, and the numbers say where the line is. A loose vault costs one object per file per fetch and
one per push; its strengths are the one-request per-path reads (the cache layer) and that any client since 0.15
reads it. A pack vault costs one listing and one batch read per clone and one zip per push, whatever the count,
and from 0.25.0 every local command on it is seconds. The crossover is not a file count so much as "how many
objects does a clone or a pull move": a few hundred objects are fine loose; thousands per pass, or tens of
thousands in the head, want the pack. A working rule for the docs: **under 5,000 files and a few hundred objects
per day, either; above that, `--packs`**; and the evidence vaults (hundreds of sources, many readers wanting one
file) stay loose with the cache layer. The flat index of section 4 is what makes a pack vault also answer the
reader's question "where is this file" without a clone, so the two modes converge on reads.

## 6. In LETS terms

Load (the host's packs and refs), extract (decrypt and verify, per object), transform (flatten, diff, scan),
save (the caches). 0.25.0 made the transforms incremental and saved their results locally; the remaining cost is
that every clone repeats the transform the pusher already did. The pack is the place where "computed once,
everybody benefits" is a file next to the data it describes. That is the index to bring back: not per path, per
head; not a registry, one immutable object; not trusted, verified; and losable.
