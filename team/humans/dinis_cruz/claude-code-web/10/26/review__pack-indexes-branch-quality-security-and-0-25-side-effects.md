# Review: the pack-indexes branch — quality, security, and side effects on 0.25.0 vaults (26 Oct 2026)

**Scope:** `c3f410ba..a9f24d8` on `claude/charming-babbage-5hzcxq` (56 source files, +3,494 / −168), the seven
commits since 0.25.0. **Method:** three independent reviewers (security; compatibility with 0.25.0 clients and
vaults; correctness of pull, checkout and pack store), each given the code and not my conclusions, each
proving findings with scripts; plus a cross-version run against the real SG/Send test server with the released
`sgit-ai==0.25.0` from PyPI and the branch build, in three shared-vault scenarios. Every finding below was
re-run by me. Nothing was fixed yet: this is the assessment.

## 1. Side effects on 0.25.0 vaults and clients: none breaking, four to know about

The cross-version run (server at `sgraph-ai-app-send`, `tests/integration`'s fixture, in-memory storage):

| Scenario | Result |
|---|---|
| A. a pack vault the new client made and pushed; 0.25.0 clones, pulls, pushes; the new client compacts; 0.25.0 pulls, verifies, pushes again; a fresh 0.25.0 clone after compaction | every command OK; trees identical at every hop; `pack verify` ok on path-ordered packs |
| B. a pack vault only 0.25.0 wrote; the new client clones (full, `--no-checkout`, `--pack-store`, `--path`), pulls, pushes, runs `pack index build`; 0.25.0 pulls and verifies between | every command OK; trees identical |
| C. a loose vault shared by both, interleaved commits and pulls | every command OK; trees identical |

Why nothing breaks, with the code: 0.25.0 never lists `bare/packs/indexes/` (its `list_folder` filters on
`commits/` and `snapshots/`); it ignores the unknown feature `pack-indexes` (`Vault__Format.check_client`
returns once the build is at or above `min_client`, and no `FEATURE_MIN_CLIENT` entry raises the gate);
extraction and `pack verify` do not depend on member order; the pack name regex, `packs_absorbed.json`,
`remote_heads.json`, flat-cache v2 and scan-cache v2 are unchanged; `Schema__Local_Config.from_json` ignores
the new `pack_store` key, so 0.25.0 reads a config the new client wrote.

The side effects that are real:

| # | Population | Effect | Severity |
|---|---|---|---|
| S1 | 0.25.0 **sparse** clones (loose vaults) | `sgit fetch` with no path, or `--all`, now goes through `checkout --all`, which clears the sparse flag and removes the record: the clone becomes full, and on-disk absences become deletions at the next commit. 0.25.0's `sparse_fetch` never flipped the flag. | Medium: a semantic change on an existing clone type |
| S2 | any pack vault, old or new | every push by the new client uploads an index pack beside its data pack (one more batch write, at least 16 KiB each because the header is padded), feature or not; on a 0.25.0-created vault nobody reads them until `sgit pack index build` runs, which also writes the `pack-indexes` feature into the branch index (a CAS write other clones may contend with) | Low: host bytes and one write per push |
| S3 | `sgit dump` (both versions) | takes every file under `bare/packs/indexes/` for a branch index (`'/indexes/' in f`) and reports a decrypt error per index pack; the dump is otherwise fine | Medium as noise in a check tool |
| S4 | 0.25.0 compaction of a vault with index packs | 0.25.0 does not move index packs to `indexes/archive/`, so orphans accumulate; the new client only reports them (`pack index verify` → orphans); the docstring's "deleted by the next run" is not implemented | Low |
| S5 | request counts (pack vaults) | push: 3 batch writes instead of 2; pull with new packs: 3 listings instead of 2 (0 extra when up to date); fresh clone: 4 listings instead of 2; compaction: about three more listings per moved pack. A scoped clone's ranged reads cost two requests per range (the presigned URL is fetched per `read_range`) and two per pack for the directory; `sgit serve` and memory hosts answer 400 and the client falls back to whole packs after one failed call | Low; Medium for scoped clones on S3 hosts |
| S6 | branch builds | the branch's `sgit_ai/version` says 0.24.3 (the pipeline bumps it on dev), so a vault **created by 0.25.0** refuses the branch build by its own gate (`min_client = max(build, 0.24.0)` at init). The merge fixes it; until then test against 0.25.0-created vaults with the version file set | Info |

Also worth knowing: a `--pack-store` clone must not be opened by 0.25.0 (its `bare/data/` is empty: 0.25.0 would
refetch); the status line `Sparse mode: n/m file(s) fetched locally` is now `Selective working copy: n/m
tracked file(s) checked out` (JSON keys unchanged); `sgit checkout main` out of git habit prints "not a tracked
file" and exits 1 (`sgit branch checkout` switches); every new flag defaults off.

## 2. Findings in the new code (ranked)

| # | Severity | Where | What | Fix |
|---|---|---|---|---|
| F1 | **High** (data loss) | `Vault__Sync__Checkout.checkout`, `:42-43` | `checkout --all` calls `_make_full` even when blobs failed to download (`missing` non-empty): the clone becomes full, status shows those files deleted, the next commit of anything else deletes them from the vault for everyone. Proven on a loose sparse clone with one blob removed from the host. | call `_make_full` only when `not missing`; otherwise refuse as the clone's `_refuse_incomplete` does |
| F2 | **High** (data loss) | `Vault__Sync__Checkout.checkout`, `:40` | `checkout <path>`, `--all`, `--changed-since` and `fetch <path>` overwrite an uncommitted edit with HEAD, no warning (the pull has `Vault__Pull__Guard`; this path has nothing). `sparse_fetch` had the same hole, but `--all` and `--changed-since` are new and touch many files at once. `--since-pull` is safe only because the preceding pull's guard blocks. | scan the directory (`_scan_local_directory(verify=wanted)`), skip paths whose hash differs from HEAD and report them as kept |
| F3 | **Medium** (security, integrity) | `Vault__Pack_Index__Reader.seed_head_flat` → `Step__Pull__Merge.write` → `_remove_deleted_flat` | A commit index whose `folder:` member omits an unchanged file passes the root anchor; the puller's merge deletes that file from disk, status is clean, and the victim's next commit removes it from the vault under the **victim's** key. Attacker: a write-key holder (with `signatures-required`, any key in `bare/keys/`), the same trust as a commit, but the lie becomes someone else's attributed commit and persists through `_flatten_incremental`. TM-R42 accepted "the working copy holds what the index says"; this goes a step further. | anchor every folder member of a commit index to its own tree (`_entries_by_name(member['tree_id'])`: all trees are local on a pack vault, and a commit index carries only changed folders, so cost follows the change), drop the index on a mismatch; then TM-R42 keeps the below-root gap for the snapshot `flat` only |
| F4 | Medium | `Step__Pull__Merge.py:246-249` (rewind path) | `--accept-rewind` on a selective clone: the guard is called without the checkout set, so on a pack vault every never-checked-out file reads as deleted and blocks; and the rewind write bypasses `write()`, so it would write every file. | pass `selective` to the guard and route the write through `write()` |
| F5 | Medium (pre-existing) | `Step__Pull__Merge.py:70-71`, `_checkout_flat_map` | a commit that replaces folder `x/` by file `x`: the write hits `IsADirectoryError` (swallowed), then the prune empties `x/`; the puller's disk lacks `x` and its next commit deletes it. Unchanged since before the branch. | prune before writing, or retry a failed write after the prune |
| F6 | Low (security, availability) | `Vault__Pack_Ranges.scoped_fetch`, `:267-268` | a scoped fetch records a pack as absorbed even when a member was refused; with the head commit then local, later pulls never re-fetch and raise "Pull incomplete" for good. One corrupt range from a flaky host wedges the clone. | exclude packs with refusals from `record_absorbed`, and re-run the scoped fetch when the head's trees or blobs are missing, not only its commit |
| F7 | Low (security, resource) | `Vault__Pack_Index.open_member`, `:95` | `zlib.decompress` with no plaintext cap (ciphertext is capped at 256 MiB): a write-key holder can make every reader allocate up to ~1000×. Before any write; deflated blobs have the same exposure today. | `decompressobj().decompress(data, max_length=PLAIN_MAX)` and refuse on `unconsumed_tail` |
| F8 | Low (latent) | `Vault__Pack_Store._handle`, `:202-217` | handle eviction is not thread-safe: an fd can be closed under another thread's `pread`; not reachable today (no threaded caller loads from packs) but the docstring promises it | refcount handles or open per read |
| F9 | Low | `Step__Pull__Merge.py:71` | `pull --no-checkout` still deletes files on disk (the docstring says it writes nothing); safe (the guard blocks an edited file) but surprising | skip the prune under `no_checkout`; let `checkout --since-pull` report it |
| F10 | Low | `Vault__Object_Store.packs()` | caches `None` for the instance's life; a store built before the table exists never sees it. No production path hits it today. | re-probe when `pack_store is None` and the file now exists |
| F11 | Low (cosmetic) | `Vault__Sync__Pull._fetch_missing_objects` | `n_commits = len(between)` is capped at 5,000 while the lines printed are `between[:500]`; a pull far behind says "N new commits" with 500 lines | cap both, or say "first 500 of N" |
| F12 | Low (latent) | `Vault__Packs.sync_down`, `take()` | `fetch_packs` keys by name and by file id; a data pack and its index pack of identical byte size would share the name key | read `got[e['file_id']]` |

## 3. What the reviewers checked and found sound

- **Zip parsing on host bytes** (index header, central directory, zip64, ranged members): bounded slices, can only raise, never write; stdlib `zipfile` for packs this client wrote.
- **Nothing written before content-address verification**: ranged members through `Vault__Verified_Write`; pack-store intake indexes only members that hash to their id and re-verifies on every read; the index plan only *names* objects and the pull checks every one is local; a refused pack member still forces the walk, and `_find_missing_blobs` still runs after an index plan.
- **Path containment**: folder members reject `/` and empty names; every write still goes through `Vault__Path_Guard`; pack, index and directory file names on disk come from the pack name regex and constant folders.
- **Signature policy**: the header is signed over canonical JSON including the key id, member hashes and offsets; the policy fails closed when it cannot be read; the trust set is the commit chain's.
- **`read_range`** keeps the presigned rules (https, or http to loopback or the vault's own http host; redirects checked; 200 answers sliced).
- **New plaintext under `.sg_vault/local`**: directories, generations and the pack-store table hold ids, offsets and numbers only; the checkout set and last-pull hold paths and are named in TM-R41; all 0600.
- **Selective working copy**: the dirty guard on fast-forward and three-way merges honours the checkout set; `--since-pull` never resurrects a locally deleted file; conflicts write `.conflict` files only for checked-out paths; a merge deleting a never-checked-out file leaves status clean; a local uncommitted deletion still commits.
- **Index assembly** equals a full walk for folder→file, file→folder, a whole-folder move, and a chain crossing a merge; a merge's second-parent side is in the plan because `_commits_between` adds all parents.
- **Pack store**: loose copies are removed only for verified members; the compaction swap keeps every object reachable; 2,400 concurrent loads over 20 packs with 8 threads gave no error (F8 is about a window that no caller opens today); `extract` clears the flag.
- **Path order**: `build_*_pack` and `_move_to_archive` order identically; an id-ordered 0.25.0 pack re-archived in path order has the same size and members (only name and size are compared) and `pack verify` passes on it.
- **Hermetic suite** 4,677 passing; integration 75 passing on the real server.

## 4. Recommendation

Before this branch goes to dev: fix F1, F2 and F3 (half a day together: a dirty scan in `checkout`, a refusal
on missing blobs, and per-folder anchoring in the reader with a `Known_Gaps` update), plus F4 and F6 (an hour).
S1 deserves a decision: keep `fetch --all` meaning "become a full clone" (then say so in its help and the
CHANGELOG) or keep 0.25.0's behaviour (fetch everything, stay sparse) and reserve the flip for `checkout --all`.
S3 is a one-line filter in `Vault__Dump`. The rest can ride with the next release. The threat-model wording of
TM-R42 should change with F3: commit-index deltas become exact, and the below-root gap is the snapshot's `flat`
alone.

Proof scripts (not part of the suite) are under the session scratchpad: `review-sec/`, `review-quality/`,
`review-compat/`, and `xver/` (the cross-version harness: `server.py` for the 3.12 venv, `xver.py` driving
`sgit-ai==0.25.0` and the branch build).
