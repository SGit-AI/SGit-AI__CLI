# Review: the pack-indexes dev pack (cli.sgit.ai/dev/pack-indexes, 26 Oct 2026)

**Read:** the dev pack (index, 01 format, 02 writer, 03 reader, 04 compatibility/security/tests), the three
articles behind it (*Indexes in the pack*, *Indexes the writer pays for*, *A vault is already a graph*), the
measurements page, the 0.25.0 release notes, and the research index. Checked against the CLI at `c069475`.
**Verdict:** ready to implement. Phase 1 is specified to the level of function names and member schemas, every
code claim I could check holds, it needs no new dependency, and it is better than the architecture I wrote
yesterday in the five places where it differs. Section 4 lists what to settle before the first line of code,
and section 5 adds the one thing the brief of this afternoon asks for that the pack does not yet have: a
working copy the agent builds selectively.

## 1. What I checked against the code

| Dev pack claim | Code | Holds |
|---|---|---|
| 0.25.0 refuses an unknown pack member individually, writes the rest, and `sync_down` then leaves the pack unrecorded, so it is re-downloaded on every pull | `extract_pack`: `member_is_safe` per member, `refused.append; continue`; `sync_down` records only packs with no refusal | yes: my "refused whole" was wrong; indexes must not live inside data packs |
| 0.24.0–0.25.0 never list `bare/packs/indexes/` | `sync_down` lists `PACK_SNAPSHOTS` and `PACK_COMMITS` only | yes: a separate index pack is invisible to old clients, so no gate is needed |
| The header can be signed like a commit | `Vault__Commit.signing_bytes` (canonical JSON) and `PKI__Crypto.sign` exist; the clone key is loaded at commit time | yes |
| Members can use the tree primitive | `Vault__Crypto.encrypt` (random IV, AES-GCM) | yes |
| Ranged reads exist for Phase 2 and 4 | `Vault__API.fetch_presigned_range(url, start, end)` returns bytes, total, partial | yes; the in-memory test host has no ranged read yet (section 6) |
| The writer holds what it needs at push | the flat cache (`flatten`, `flatten_dirs`), the incremental build's changed paths, parents from the commit | yes |
| The sparse semantics the brief needs | `Schema__Local_Config.sparse`; status and commit already treat a never-fetched tracked file as "not here", never as deleted | yes, see section 5 |
| Path order keeps `MEMBER_RE` and determinism | `write_pack` sorts ids; order is the writer's choice; extraction sorts by name | yes |

## 2. Where it corrects my architecture, and I agree

1. **Index packs beside data packs, under `bare/packs/indexes/`,** same names: no member rule to change, no
   gate, old clients keep working unchanged, rollback is "stop writing them". Mine needed a format feature and
   locked out 0.25.0. Theirs is strictly better.
2. **No SQLite, no graph engine, no new dependency.** Their measurements say dicts win for every question sgit
   asks (a 7,600-file folder: 2.2 ms in dicts, 48 ms in SQLite, 131 ms in Oxigraph; a merge base with
   generation numbers: 0.1 ms). Ship JSON members typed at the writer, load dicts at the reader. The local
   graph view stays optional, outside the CLI.
3. **Indexes stay encrypted on disk; assembly is in memory.** Nothing new in clear (T10), and it is already
   what sealed vault keys will need. Mine put a plaintext SQLite under `local/`.
4. **Generation numbers in the index, not in commits.** Same idea, without touching `commit_v1`.
5. **Members as sequence numbers with meaning only in the signed header, and an offset table first** so a
   reader opens a 58,598-member index in 50 ms instead of parsing the central directory in 910 ms.

Two things it adds that I did not have and that matter most to the newsroom: **path-ordered data packs with
`at` offsets** (one folder = one contiguous range: `raw/c09/s4/`, 1,520 files, 0.22 MB in one range instead of
30.4 MB in 265), and **folder members with subtree totals and both-way cross-references** (which paths hold a
blob, which commits changed a file), which are the questions the curator and the journalist ask.

## 3. Numbers I trust and numbers I will re-measure

The prototypes are honest about being prototypes. Three figures carry the design and are solid: the flat
member (2.42 MB deflated, 0.58 s to inflate and parse 76,000 entries), the commit delta (3.1 KB for five
files, 0.92 s for 1,000 commits), and reading an object in place (5 µs). The ones I will re-measure in sgit
itself before claiming them: the "first command after clone 0.58 s" (today the clone seeds the flat cache
anyway, so the gain is the tree walk on a pull of an unseen head), the pull targets (the 6 s presence check
and the stat pass are the floor on the 228,000-file vault, and the stat pass stays), and anything on a cloud
disk, which no prototype touched.

## 4. To settle before coding

1. **Signed and unsigned indexes.** 03 accepts an unsigned index on a vault without `signatures-required`.
   Agreed, with one addition: an index whose `author_key_id` is not in `bare/keys/` is treated as unsigned,
   and `sgit pack index verify` says which indexes are unsigned, so a vault that turns the policy on later
   sees what it has.
2. **`at` offsets after compaction.** A commit index's `data_packs` names older packs for unchanged files;
   compaction moves those packs to `archive/`. The reader must resolve a pack name in `commits/` or
   `archive/`, and the snapshot index written by compaction must carry `at` into the snapshot pack for every
   file. 02 says both; make the second a test (T6 extended).
3. **The `pack-indexes` feature write.** Adding a feature to the branch index is a CAS write of the index;
   do it in the same push that already rewrites the branch index when needed, never as a separate write that
   can race another client. The first index upload on an existing vault is the one case; `pack index build`
   does it under the same CAS.
4. **The reserved header size.** The grow-and-retry layout (R in 16 KiB steps, 4 KiB slack) is fine. I would
   also write the header's `L` into the zip comment so a reader that *does* have the central directory can
   skip the 30-byte probe; cheap, optional.
5. **Memory per command.** The reader assembles the flat map and cross-references in memory on first use:
   on the 228,000-file vault that is ~60 MB of dicts per process, built in ~1.5 s. Acceptable for a CLI run;
   note it in the limits. A later on-disk assembly (encrypted) is the stated option.
6. **Phase order.** The pack says 1, 2, 3, 4. I would run 1, then the selective working copy of section 5,
   then 3 (the pack as the store, which is what the cloud disks pay for), then 2, then 4. Section 5 explains
   why the working-copy change comes early.
7. **Windows and the pack store (Phase 3).** A kept pack is an open file; compaction's local swap and
   `vault move` must close handles first. Put it in T9.

Everything else in the pack I would implement as written.

## 5. The brief of this afternoon: the agent builds the files it needs

The newsroom's loop is: the researchers push a pass of new material; the curator pulls and needs to read
**the new files**, not the 79,000 it already has. Today a pull writes exactly the changed files (0.25.x), which
is right, but the clone itself wrote all 79,000 at clone time, and a fresh container clones every wake.

The dev pack's Phase 2 (`clone --path <folder>`, one ranged read per folder) covers "I want this folder". The
curator's case is different: "I want whatever the last passes added, wherever it is", and later maybe one
folder for a deeper look. That is a **selective working copy**: the clone holds the whole index (and, with the
pack store, the whole pack), and materialises files on demand, by path or by change.

What it needs, and what already exists:

| Piece | Exists | To add |
|---|---|---|
| a clone whose working copy is a subset of the head, where a tracked file that was never written is "not here", not "deleted" | yes: `sparse` clones (`Schema__Local_Config.sparse`); status, commit and pull already honour it | make it reachable for pack vaults: `sgit clone --packs --no-checkout` (index and packs only, no files) |
| "which files did the last passes add or change" | Phase 1's `changes` members, and today's pull listing | `sgit pull --no-checkout` prints the changed paths (and `--json` lists them) instead of writing them |
| materialising a path | `_checkout_flat_map` over a sub-map; `sgit fetch <folder>` widens a scoped clone | `sgit checkout <path> [...]`, `sgit checkout --changed-since <commit>` and `--since-pull`: write those files from local objects (loose today, in place with the pack store), seed the scan cache, record them as materialised |
| a commit from a selective working copy | yes: a sparse commit overlays the on-disk files on the parent's flat map | nothing; the new files the curator writes alongside are committed as today |
| status on a selective working copy | yes, sparse rule | report "N tracked files not checked out" once, so it is never mistaken for a deletion |

With the pack store (Phase 3) a `checkout` of a folder is a local seek per file; without it, it is a loose
read per file, also local. Either way no network, and the curator's wake becomes: `clone --packs
--no-checkout` (packs and indexes, no files), `pull --no-checkout` (lists what the researchers added),
`checkout --since-pull` (writes just those), read, write its own files, `commit`, `push`. On the newsroom's
vault that replaces 79,000 file writes with a few thousand.

Size: about two days on top of Phase 1, because every mechanism is the sparse clone's; the work is the three
flags, the materialised-set record, and the status line, with tests on the two-clone in-memory host.

## 6. What I need to implement, and have

- **No new dependency**: `zipfile`, `zlib`, `json`, the existing `cryptography` use, osbot-utils' Type_Safe for
  the writer-side schemas. The pack is explicit about this and the code agrees.
- **Test hosts**: the in-memory host (`Vault__API__In_Memory`) and the counting host (`Host__Counting`) cover
  Phase 1 and the selective working copy. Phase 2 needs a ranged read on the in-memory host (`read_range`):
  an hour. Phase 4 needs the live API's presigned range, which exists.
- **Benchmark vaults**: the 228,000-file synthetic vault and its stores are in my scratch space; the 76,000-file
  vault's generator (`vault/genbig.py`) is on the site. The newsroom's own vault is not needed; its key stays
  with them.
- **Fuzzer**: the site's fuzzer (16 seeds, ~450 commits) is the T1 oracle; I will port its shape into
  `tests/unit/pack/` so T1 runs in CI on the in-memory host.
- **Threat model**: TM-R42 (path order) and the index rows of 04 go into `v0.21.0__threat-model.md` with a
  `Known_Gaps` test each where a gap is accepted.

## 7. Plan, with sizes

| Step | What | Days |
|---|---|---|
| 1 | Phase 1 writer: `Vault__Pack_Index` (build, lay out, sign, encrypt, write), schemas, push/compaction/import hooks, `pack index build/verify/stats`, gaps file | 2.5 |
| 2 | Phase 1 reader: find, verify, assemble in memory; pull (commit list, merge base, missing blobs, flat map), `history log`, first flatten after clone; fallbacks; T1–T6, T10, C1 | 2.5 |
| 3 | Selective working copy (section 5): `--no-checkout`, `checkout <path>` / `--since-pull`, status line, sparse-on-packs tests | 2 |
| 4 | Phase 3 pack store: packs kept, pack index, read in place, verify on first read, fsck, compaction swap, Windows handle rule; T9; cloud-disk measurement with the newsroom | 3 |
| 5 | Phase 2: path-ordered packs (scope-grouped), `at` offsets, ranged scoped clone and pull; T7, T8; TM-R42 | 3 |
| 6 | Phase 4 with the SG/Vault team | — |

Steps 1 and 2 are one release (the writer is useless without the reader and vice versa); step 3 rides with
them if it is ready; 4 and 5 are each their own release behind their flag, as 04 says.
