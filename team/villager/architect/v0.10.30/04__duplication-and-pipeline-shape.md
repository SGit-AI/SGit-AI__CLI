# Finding 04 — Duplication and pipeline shape

**Verdict:** `BOUNDARY DRIFT` — significant duplication, all on the Dev side
of the line. **No SEND-BACK-TO-EXPLORER required**: the boundaries are
correct, it's just that the same algorithm shows up multiple times.

**File health:** `sgit_ai/sync/Vault__Sync.py` is **2,986 lines** as of v0.10.30.
This was 2,200-ish at v0.13.30 review (qualitative recall). Of the 22 commits
hitting this file in 14 days, ~6 added pipeline code that closely mirrors
existing pipeline code.

---

## 1. The two BFS implementations

`_clone_with_keys` (lines 1276–1417) and `_fetch_missing_objects` (2334–2526)
**both implement the same Phase-1 + Phase-2 + Phase-3 BFS pattern** to walk
commits, then trees, then collect blobs.

Side-by-side outline:

| Step | `_clone_with_keys` | `_fetch_missing_objects` |
|---|---|---|
| BFS commits | lines 1356–1377 | lines 2384–2427 |
| BFS trees | lines 1387–1408 | lines 2434–2459 |
| Collect blobs | delegates to `_clone_download_blobs` (1957) | inline (lines 2461–2477) + Pass-2 download (2498–2522) |
| Visited-set semantics | `visited_commits`, `visited_trees` | `visited_commits`, `seen_trees`, `seen_blobs` |
| `stop_at` semantics | none | yes (pull stops at locally-present commits) |
| Per-wave batch_save | inline | extracted to `_batch_save` closure |
| Save-file helper | `save_file` closure (1297) | `_save` closure (2356) |
| Progress phases | `scan` / `scan_done` per phase | same |
| Decrypts commit message | NO | yes (lines 2484–2492) — for the per-commit `commit` log line |

Major shared logic, two implementations. Risk:
- A future bug fix to one (e.g. a `visited` check) won't propagate to the
  other.
- The `stop_at` optimisation (which made pull fast — see commit `664f41c`)
  exists only in the pull path; clone could in theory reuse it once a clone
  is converted from sparse to full.

**Recommended (for Dev sibling, NOT for me to implement):** extract a
`Vault__Graph_Walk` (or similar) `Type_Safe` class that owns the BFS state
machine and is parametrised by:
- starting frontier (1+ commit IDs)
- stop predicate (`stop_at` set, locally-present check)
- whether to descend into trees, descend into blobs
- per-wave callbacks (for progress)

Both `_clone_with_keys` and `_fetch_missing_objects` then become orchestrators
that configure and call this class.

This is a Phase-3 refactor candidate. **Not in scope for Architect to
implement.** Filing for Dev to schedule.

## 2. The two "build tree from flat map" pipelines

`Vault__Sub_Tree.build` (24–113) and `Vault__Sub_Tree.build_from_flat`
(115–188) are **near-identical 90-line procedures**. The only differences:

- `build` reads file content from disk and encrypts it; `build_from_flat`
  trusts the existing `blob_id` from the flat map.
- `build` does its own content-hash dedup against `old_flat_entries`;
  `build_from_flat` skips that step (because the caller — typically `merge`
  or `write_file` — has already resolved blob identity).

Everything else (the dir_contents map, the all_dirs set, the sorted_dirs walk,
the per-dir tree assembly, the folder-entry loop) is duplicated almost
verbatim. The duplication is ~140 lines, not a small smell.

**The HMAC-IV change had to be applied in BOTH methods** (commit `4d53f79`
edited 24 lines across both). This is exactly the kind of thing duplication
penalises — if a future call-site forgets one or the other, the determinism
invariant breaks for that path.

**Recommended for Dev:** extract the shared structure into
`_build_tree_from_dir_contents(dir_contents, all_dirs, entries_provider, read_key)`
where `entries_provider` is a callback that knows how to produce the
`Schema__Object_Tree_Entry` for a given (dir_path, filename). `build` and
`build_from_flat` then become 20-line wrappers.

## 3. The "write file pipeline" vs "commit pipeline"

`Vault__Sync.write_file` (227–335) re-implements the spine of `Vault__Sync.commit`:
- Load HEAD flat map (same as commit).
- Per-file content-hash dedup (same as commit, same as `Vault__Sub_Tree.build`).
- Build root tree via `sub_tree.build_from_flat` (same as merge, same as rekey).
- Create commit + write ref (same as commit).
- Optionally write working-copy file (NEW — commit reads working dir, doesn't
  write back to it).

That's three implementations of "encrypt blob if changed, otherwise reuse":
1. `Vault__Sub_Tree.build` (lines 68–76) — full-scan path.
2. `Vault__Sync.write_file` (lines 275–294) — surgical path.
3. (Pre-existing, conceptually) the merge path.

The dedup logic is short enough that triplication isn't catastrophic, but the
risk is: a future tweak (e.g. a new `large` threshold, a new content-type
inference rule) has to be made in three places. The HMAC-IV change is one
example of "cross-cutting tweak that touches multiple sites".

**Recommended for Dev:** extract `Vault__Sub_Tree.encrypt_or_reuse_blob(
content, old_entry, read_key)` returning `(blob_id, is_large, was_reused)`.
Both `build` and `write_file` use it.

## 4. The rekey pipeline (NEW) and its overlap with init+commit

`rekey` is `rekey_wipe → rekey_init → rekey_commit`:
- `rekey_wipe`: rmtree `.sg_vault/`.
- `rekey_init`: calls `self.init(directory, vault_key=new_vault_key, allow_nonempty=True)`.
- `rekey_commit`: calls `self.commit(directory, message='rekey')`.

This is a **good** pattern — rekey IS init + commit, and the implementation
honestly composes them. No new pipeline introduced. The wizard UX in
`cmd_rekey` is the only new surface, and it's the right place for it.

The `allow_nonempty=True` flag is new — added to `init` so rekey doesn't trip
the "directory not empty" guard. This is a clean parameter extension.

## 5. The sparse vs full clone code paths

`_clone_with_keys` carries a `sparse: bool` parameter that gates Phase-5
(`_clone_download_blobs`). `_clone_download_blobs` (1957–2042) was extracted
in the sparse-clone commit. The extraction was tidy — no remnants of the
inline version remain.

**`sparse_fetch` (2098–2175) DOES re-implement small/large blob bucketing**
that's already done by `_clone_download_blobs` (1990–2003 vs 2128–2162).
Same rationale (Lambda-safe response size, large-blob threshold). Same risk:
if the threshold ever changes (e.g. server raises the Lambda limit), both
sites need updating.

**Recommended for Dev:** extract `Vault__Object_Store.batch_download_blobs(
vault_id, blob_specs, on_progress)` that owns the small/large bucketing.

## 6. Summary scoreboard

| Duplication site | Severity | Refactor candidate |
|---|---|---|
| BFS in clone vs pull | HIGH (~150 lines, missed-fix risk on `stop_at`) | `Vault__Graph_Walk` |
| `Vault__Sub_Tree.build` vs `build_from_flat` | HIGH (~140 lines, HMAC-IV almost missed) | extract dir-walk core |
| `write_file` blob-or-reuse vs `Sub_Tree.build` blob-or-reuse | MEDIUM (~30 lines) | `encrypt_or_reuse_blob` helper |
| `_clone_download_blobs` vs `sparse_fetch` blob bucketing | MEDIUM (~50 lines) | move bucketing into `Vault__Object_Store` |
| File-write loop in `_clone_download_blobs` vs `sparse_fetch` vs `_fetch_missing_objects` | LOW (~10 lines each) | already covered by extracting the bucketing helper |

`Vault__Sync.py` at 2,986 lines is past the threshold where individual
methods are easy to navigate. Splitting it (Phase 4 candidate) into
`Vault__Sync_Clone`, `Vault__Sync_Pull`, `Vault__Sync_Push`, `Vault__Sync_Edit`
(write/rekey/delete) is a natural axis. **Out of scope for me to do** — but
worth noting now so it stays on the Dev/Sherpa radar.

## 7. Hand-off

- **Dev (HIGHEST PRIORITY for Phase 3):** `Vault__Graph_Walk` extraction.
  Single biggest reduction in code-mass with the highest correctness payoff
  (one BFS bug fix, applied once).
- **Dev (Phase 3, secondary):** `Vault__Sub_Tree.build` / `build_from_flat`
  unification. Driven by the HMAC-IV near-miss.
- **Sherpa:** decide on the `Vault__Sync.py` split for Phase 4.
- **QA:** parameterise the BFS tests (if any exist) to run against both
  current implementations, so the extraction can be verified for behavioural
  equivalence.
