# Brief 18 — Clone does not download historical blobs (🔴 data-loss risk)

**Date:** 2026-05-07
**Found by:** Dinis Cruz (live `sgit vault move` session)
**Severity:** 🔴 Critical — silent data loss on vault move; degraded history commands on every clone
**Status:** Root cause confirmed; fix specified below
**Audience:** SGit Dev Agent
**Scheduling:** **JUMPS TO FIRST in the v0.14.x queue** — ahead of every other pending brief. Estimated effort: ~1 day.
**Author:** Villager orchestrator (Opus) — extending the executor's earlier debrief.

---

## 1. How it was found

A vault was freshly cloned from the server. `sgit vault move` was then run on
the clone. The Brief 15 §2a integrity check (commit graph walk added to
`Step__Move__Validate_Local`) fired:

```
error: Local vault is missing 35 object(s) referenced by the commit graph
(e.g. obj-cas-imm-...). The move would ship an incomplete vault to the server.
Run `sgit pull` or `sgit fetch` first to complete the local clone before
retrying vault move.
```

Initial hypothesis: the missing objects belonged to **other cloners' branches**
(a known limitation). That theory was disproved when `sgit check fsck` was run
on both the original local vault and a freshly cloned copy:

```
$ sgit check fsck .           # run on a fresh clone
  ▸ Checked 59 commits, 1 trees
  Missing objects: 234
    ! obj-cas-imm-<...>       # same IDs repeated
    ! obj-cas-imm-<...>
    ... and 224 more
```

A clone that just finished downloading reported **234 missing objects
immediately** — before any other operation.

---

## 2. What the evidence shows

| Operation | Reported number |
|-----------|----------------|
| Clone: commits walked | 59 |
| Clone: trees walked | 415 |
| Clone: blobs downloaded | 165 |
| fsck: objects missing after clone | 234 |

The clone walked 415 trees across the full commit history but downloaded only
165 blobs. `fsck` then walked the same 59-commit chain and found 234 objects
missing locally.

---

## 3. Root cause

The clone's blob-download step fetches **only the blobs needed to reconstruct
the current HEAD working copy** — i.e., one blob per file that currently exists
in the vault's latest state.

It does **not** download blobs for historical versions of files that have since
been modified or deleted.

In a content-addressable store, every unique version of every file is a
separate blob object. A vault with 59 commits and active file churn will have
far more blob objects in its history than it has files in its HEAD tree.

**Concretely:**
- If `README.md` was committed 10 times, there are 10 distinct blob objects.
- Clone downloads the HEAD version (1 blob).
- The 9 historical versions remain on the server but are not downloaded.
- `fsck` flags the 9 historical blobs as missing → correct, they are.

---

## 4. Impact

### 4a. Vault move creates an incomplete new vault (🔴 data loss)

`Step__Move__Build_Temp_Vault._reencrypt_objects` iterates `os.listdir(bare/data/)`.
Only locally-present objects get re-encrypted and pushed to the new vault.
Historical blobs that were never downloaded are silently absent from the new
vault.

After the move:
- Old vault is tombstoned (permanently deleted).
- New vault is missing all historical file versions.
- Anyone cloning the new vault and running `sgit history show <old-commit>`
  gets decryption errors for any file that changed between that commit and HEAD.

**The Brief 15 §2a integrity check prevented this.** Without it, the move would
have completed silently and the data loss would only be discovered later (or
never, if no one inspects history).

### 4b. History commands are degraded on any clone

`sgit history show`, `sgit history diff`, and `sgit history log --patch` all
need to decrypt historical blobs. Those commands will fail or silently produce
incomplete output on any cloned vault because the historical blobs were never
downloaded.

### 4c. `sgit check fsck` duplicate output (minor bug)

The `fsck` output lists the same object ID multiple times (e.g., the same blob
is referenced by 4 different historical tree objects and therefore appears 4
times in `result['missing']`). The list is not deduplicated before printing.
This inflates the reported "Missing objects" count and makes triage harder.

---

## 5. What the Brief 15 fix saved

Without the `Step__Move__Validate_Local` commit graph walk:

1. Move would have appeared to succeed.
2. New vault on server would have been silently incomplete.
3. Old vault would have been tombstoned.
4. Data recovery would require: knowing which objects were missing, having the
   old vault key, and the old vault not having been garbage-collected.

The fix correctly blocked the move and gave a clear error. The error message
("run `sgit pull` first") is wrong — pull has the same selective-download
behaviour — but the abort is the right outcome.

---

## 6. Fixes required

### Fix A — Clone must download ALL historical blobs (critical)

The blob-download step in the clone workflow must be changed from
"blobs needed for HEAD checkout" to "all blobs reachable from the full commit
chain."

This is the canonical definition of a full clone in any content-addressable
VCS. The current behaviour is closer to a shallow/sparse checkout.

File to change: wherever the clone's blob download loop runs (the step that
produced "Downloading blobs [165/165]").

### Fix B — Move must fetch missing objects before re-encrypting (defence-in-depth)

Even after Fix A, a future clone could miss objects due to a network
interruption or another edge case. The move workflow should:

1. Run the commit graph walk (already done by Brief 15).
2. If objects are missing, attempt to fetch them from the old vault server
   (the old vault is still live at this point and the credentials are available).
3. Only abort if fetch fails — not on first discovery of a gap.

`sgit check fsck --repair` already implements the per-object fetch logic
(`_repair_object`). The move workflow can reuse it.

### Fix C — Dedup missing-object list in `fsck` output (minor)

Change `result['missing'].append(oid)` to check membership first, or
deduplicate before printing. The count and the list should reflect unique
object IDs.

### Fix D — Update error message in move (low priority)

"Run `sgit pull` or `sgit fetch` first" is misleading because pull/fetch have
the same selective-download behaviour. Change to:

```
Run `sgit check fsck --repair` to download all missing objects from the
server before retrying vault move.
```

---

## 7. Order of work

1. **Fix A** — clone full history blobs. This is the root cause fix.
2. **Fix C** — dedup fsck output (quick, unblocks triage).
3. **Fix B** — move auto-repair (defence-in-depth, can land after Fix A).
4. **Fix D** — error message (trivial, anytime).

Fix A must land before any user runs `sgit vault move` on a cloned vault.

---

## 8. Implementation outline (added by Villager Opus)

### 8a. Fix A — collect blob IDs during the tree walk; download all of them

**Where the bug lives:** `sgit_ai/core/actions/clone/Vault__Sync__Clone.py:290-298` — `_clone_download_blobs` calls `sub_tree.flatten(str(commit_obj.tree_id), read_key)` on the HEAD commit only. That returns only the blobs reachable from the HEAD tree, ignoring every other commit in the chain.

**Where the existing tree walk is:** `sgit_ai/workflow/clone/Step__Clone__Walk_Trees.py:26-44` — `Step__Clone__Walk_Trees` already walks every reachable tree from `root_tree_ids` (which `Step__Clone__Walk_Commits` populates with EVERY commit's root tree, not just HEAD's). So tree coverage is already complete; only blob enumeration is broken.

**The fix:** collect blob IDs as a side-effect of the tree walk that already happens in `Step__Clone__Walk_Trees`, then have `Step__Clone__Download_Blobs` download every blob ID instead of re-flattening from HEAD.

#### Step 1 — Extend `Schema__Clone__State`

In `sgit_ai/schemas/workflow/clone/Schema__Clone__State.py`:

```python
class Schema__Clone__State(Type_Safe):
    ...
    all_blob_ids : list[Safe_Str__Blob_Id]    # NEW: every blob id reachable from any tree
```

Use the existing `Safe_Str__Blob_Id` (or whatever the project's blob-id type is — likely `Safe_Str__Object_Id` if no blob-specific type exists).

#### Step 2 — Collect blob IDs during the tree walk

In `Step__Clone__Walk_Trees.execute`, change `load_tree` to also extract blob IDs from each tree's entries:

```python
all_blob_ids = set()

def load_tree(tid):
    tree = workspace.vc.load_tree(tid, read_key)
    workspace.progress('scan', 'Walking trees', str(tid))
    # NEW: collect blob ids from every tree's entries
    for entry in (tree.entries or []):
        if entry.blob_id:
            all_blob_ids.add(str(entry.blob_id))
    return tree

visited_trees = graph_walk.walk_trees(root_tree_ids, load_tree, on_batch_missing)
...
data['n_trees']      = n_trees
data['t_trees_ms']   = t_trees_ms
data['all_blob_ids'] = sorted(all_blob_ids)    # NEW
return Schema__Clone__State.from_json(data)
```

#### Step 3 — Replace `_clone_download_blobs`'s HEAD flatten with the full list

`Step__Clone__Download_Blobs.execute` should now consume `input.all_blob_ids` directly, not call `_clone_download_blobs(named_commit_id, ...)` which re-flattens HEAD only:

```python
def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
    sg_dir       = str(input.sg_dir)
    all_blob_ids = [str(b) for b in (input.all_blob_ids or [])]

    workspace.ensure_managers(sg_dir)

    n_blobs    = 0
    t_blobs_ms = 0

    if all_blob_ids and not input.sparse:
        vault_id = str(input.vault_id)
        read_key = bytes.fromhex(str(input.read_key_hex))
        blob_stats = workspace.sync_client._download_blobs_by_id(
            vault_id, all_blob_ids, read_key,
            lambda fid, data: workspace.save_file(sg_dir, fid, data),
            workspace.progress,
        )
        n_blobs    = blob_stats.get('n_blobs', 0)
        t_blobs_ms = int(blob_stats.get('t_blobs', 0.0) * 1000)
    ...
```

Add a new `Vault__Sync__Clone._download_blobs_by_id(vault_id, blob_ids, read_key, save_file, _p)` method that takes a pre-collected list of blob IDs (instead of flattening HEAD). Reuse the existing chunking + parallel-download logic from `_clone_download_blobs` (the small/large blob split, `MAX_RESPONSE_BYTES`, ThreadPoolExecutor, presigned-URL path for large blobs). The diff is purely the input — list of blob IDs instead of "flatten this tree."

The old `_clone_download_blobs` can be removed once nothing calls it. (Or kept as a thin wrapper: flatten HEAD then call `_download_blobs_by_id`. Probably cleaner to delete and inline the chunking logic into `_download_blobs_by_id`.)

#### Step 4 — Existing per-mode workflows — verify behaviour

The thin clone modes need explicit behaviour confirmation:

| Workflow | Should download all historical blobs? |
|---|---|
| `Workflow__Clone` (default `sgit clone`) | **YES** — this is the bug fix |
| `Workflow__Clone__Branch` (`clone-branch`) | NO — by design, HEAD trees only. Keep `Step__Clone__Walk_Trees__Head_Only` step. |
| `Workflow__Clone__Range` (`clone-range`) | YES, but only blobs reachable from commits in the range. The tree walk already filters; the blob collection follows. |
| `Workflow__Clone__Headless` (`clone-headless`) | NO — no working copy, no tree walk. Unchanged. |
| `Workflow__Clone__ReadOnly` | YES — same as default clone. |

Audit each workflow's step list. The default and read-only paths use `Step__Clone__Walk_Trees`; they pick up the fix automatically. `Workflow__Clone__Branch` uses `Step__Clone__Walk_Trees__Head_Only` and stays thin (correct by design — that's what `clone-branch` is for).

For `Workflow__Clone__Range`: confirm `Step__Clone__Walk_Trees` walks only trees from the in-range commits (it does, because `root_tree_ids` is populated only from those commits in `Step__Clone__Walk_Commits__Range`).

### 8b. Fix B — move's `Validate_Local` triggers an auto-repair

In `Step__Move__Validate_Local._verify_commit_graph`, when `missing` is non-empty, attempt to fetch the missing objects from the OLD vault server BEFORE raising. The vault is still live at this point and the credentials are in scope.

```python
if missing:
    # Try to repair from the source server before giving up
    repaired = self._try_repair_missing(missing, ...)
    still_missing = [oid for oid in missing if oid not in repaired]
    if still_missing:
        examples = ', '.join(still_missing[:3])
        raise RuntimeError(...)
```

`_try_repair_missing` reuses `Vault__Sync__Fsck.repair` or a similar `Vault__API.batch_read` + save loop. After Fix A lands and is rolled out widely, this auto-repair is rarely needed — but it's defence-in-depth for any future clone that ends up incomplete (network blip mid-clone, etc.).

### 8c. Fix C — dedup `fsck` missing-objects list

In `sgit_ai/core/actions/fsck/Vault__Sync__Fsck.py` (or wherever the fsck logic lives), find the `missing.append(...)` site and convert to a set, OR deduplicate before output:

```python
# Before printing
result['missing'] = sorted(set(result['missing']))
```

Trivial.

### 8d. Fix D — error message in move's Validate_Local

Change the message in `Step__Move__Validate_Local._verify_commit_graph`:

```python
raise RuntimeError(
    f'Local vault is missing {len(still_missing)} object(s) referenced by the '
    f'commit graph (e.g. {examples}). The move would ship an incomplete vault '
    f'to the server. Run `sgit check fsck --repair` to download missing objects '
    f'before retrying vault move.'
)
```

`sgit pull` and `sgit fetch` have the same selective-download bug today (and even after Fix A, they don't backfill historical blobs on existing clones — only fresh clones do). `fsck --repair` is the canonical "make my local clone whole" operation.

---

## 9. Tests

### 9a. Unit-tier tests

In `tests/unit/workflow/clone/test_Step__Clone__Walk_Trees__Blob_Collection.py` (new):

1. `test_walk_trees_collects_blob_ids_from_every_tree` — set up a vault with 3 trees, each with distinct blob IDs; run the step; assert `output.all_blob_ids` contains all blob IDs across all trees.
2. `test_walk_trees_dedups_blob_ids` — same blob referenced by multiple trees → single entry.
3. `test_walk_trees_with_no_trees_returns_empty_list` — empty `root_tree_ids` → `all_blob_ids == []`.

In `tests/unit/workflow/clone/test_Step__Clone__Download_Blobs__From_List.py` (new):

4. `test_download_blobs_from_all_blob_ids` — given a populated `all_blob_ids`, every blob is downloaded.
5. `test_download_blobs_skips_when_sparse` — `sparse=True` → no downloads, even with populated `all_blob_ids`.
6. `test_download_blobs_handles_large_blobs` — large-blob path still works with the new list-based input.

### 9b. Integration tests (against the real local server)

In `tests/integration/test_Clone__Full_History_Blobs__Integration.py` (new):

7. `test_clone_downloads_blobs_for_every_historical_commit` — set up a vault, modify the same file across 5 commits (producing 5 distinct blobs of that file), push. Clone from a fresh dir. Run `sgit check fsck` on the clone. Assert: zero missing objects.
8. `test_clone_then_history_show_works_for_old_commits` — same setup; clone; run `history show <commit-2>` — assert it succeeds without "object not cached locally" errors.
9. `test_clone_then_vault_move_passes_validation` — same setup; clone; run `vault move`; assert the move COMPLETES (does NOT trigger the missing-objects abort).
10. `test_clone_branch_remains_thin` — explicitly call `clone-branch`; run `fsck`; assert historical blobs are NOT downloaded (clone-branch is intentionally thin). Negative regression: makes sure Fix A doesn't accidentally break the thin clone modes.

### 9c. Existing test impact

- `tests/unit/workflow/clone/` — most tests use small fixtures with one commit; no behaviour change. Spot-check that existing tests still pass.
- `tests/qa/sync/` — large multi-commit fixtures will see more blob downloads. Adjust any test that asserts a specific blob count.

---

## 10. Recovery for users with existing clones

After Fix A lands, NEW clones will be complete. **Existing local clones remain incomplete** until the user runs `sgit check fsck --repair` against the source server. Communicate this clearly:

### 10a. Add a release-note entry

In whatever changelog / release notes accompany the next sgit release:

```
[CRITICAL FIX] sgit clone now downloads historical blobs

Previously, sgit clone only downloaded blobs needed for the HEAD working
copy, not blobs for past versions of files. This silently broke `sgit
history show <past-commit>`, `sgit history diff`, and (most seriously)
made `sgit vault move` ship an incomplete vault to the server.

If you have an existing clone, run:

    sgit check fsck --repair

to download the missing historical blobs from the source server before
running ANY destructive operation (especially `sgit vault move`).

Fresh clones from this version onward are complete by default.
```

### 10b. Make `sgit vault move` warn on legacy clones

Even after Fix A, users with pre-fix clones will hit the §2a abort when they try `vault move`. The error message (Fix D) directs them to `fsck --repair`, which is correct. No additional code change needed beyond Fix D.

### 10c. Optional: `sgit check fsck` runs automatically as part of `sgit vault move --auto-repair`

If Fix B lands, the move auto-repair makes the recovery transparent. Otherwise users learn from the error message. Both are acceptable.

---

## 11. Out of scope

- **Re-cloning all existing user vaults automatically.** Users run `fsck --repair` themselves; sgit doesn't push the upgrade.
- **Schema versioning to mark "this clone has been backfilled" vs "incomplete".** Could be useful but not essential — `fsck` reports the same answer regardless of when objects were downloaded.
- **A new `sgit clone-thin` mode that's explicitly thin like the current behaviour.** Users wanting thin clones should use `clone-branch`, which already exists for that purpose.
- **CDN / Public Vault interaction.** Fix A increases the bytes downloaded on a fresh clone — for vaults with deep history, this could be significant. Future optimisation: consider whether public vaults benefit from the commit-zip / per-commit-bundle approach we'd discussed earlier (compressing each commit's full object set into one zip on the server). Out of scope for this brief.

---

## 12. Verification checklist

When done:

- All ~10 new tests pass (3 unit + 4 integration + 3 regression).
- Existing 3,442+ unit tests pass.
- Integration test: clone → fsck reports 0 missing objects.
- Integration test: clone → `history show <past-commit>` works.
- Integration test: clone → `vault move` completes without the missing-objects abort.
- `clone-branch` regression: still produces a thin clone.
- `fsck` output: missing list is deduplicated.
- Move error message: directs users to `sgit check fsck --repair`.

Estimated effort: ~1 day (Fix A ~3h, integration tests ~3h, Fix C ~30min, Fix B ~2h, Fix D ~10min, reviewer fix ~30min).

---

## 13. Why this jumps to first

Every other v0.14.x brief assumes the clone path is correct. Brief 17 (commit-id resolution) won't be useful if `history show <past-commit>` is still broken on fresh clones. Brief 12 (move cleanup) won't help if every cloned vault's move is actively dangerous. Brief 15's §2a check is currently load-bearing for safety — the moment we fix Brief 18, §2a goes from "essential" back to "defence-in-depth", which is where it should be.

**New v0.14.x landing order:** **18** → 16 → 17 → 12 → 09 → 06 → 07 → 08 → 10.

Brief 18 is the most important pending item. Land it first.
