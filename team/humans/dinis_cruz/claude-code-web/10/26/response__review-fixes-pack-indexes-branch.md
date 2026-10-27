# Response: the review findings on the pack-indexes branch, fixed (26 Oct 2026)

**Branch:** `claude/charming-babbage-5hzcxq`, five commits on top of the review document (`727f265`), not
on `dev`. **Inputs:** my own review (`review__pack-indexes-branch-quality-security-and-0-25-side-effects.md`,
F1–F12 and S1–S6) and the cli.sgit.ai build agent's review (B1–B2, M1–M6, L1–L5). Every item below is
fixed, documented, or deferred with the reason; nothing is left silent.

## Blocking and data loss

| Item | Done | Where |
|---|---|---|
| B2 / F2 `sgit checkout` overwrote uncommitted edits | fixed: the wanted paths are read as status reads them; a dirty one (or an untracked file at a tracked path) is kept and reported, never written, unless `--force`; a kept file is held by the checkout set | `596a372`, `Vault__Sync__Checkout._dirty`, CLI line `≠  path  (kept: yours, uncommitted)` |
| F1 `checkout --all` made a clone full with blobs missing | fixed: the flip happens only when every tracked file is on disk; otherwise the clone stays selective and says so; the CLI's "now a full working copy" follows the result, not the flag | `596a372` |
| F3 a lying commit-index folder member made every puller delete a file | fixed: every folder member of a commit index is anchored to its tree object (files with entries, child folders with ids, nothing more or less) before it touches a flat map; mismatch drops the index; the snapshot `flat` keeps the root anchor (TM-R42 narrowed) | `b59aa14`, `test_Security__Fixed__Lying_Index` (5) |
| B1 push walked the whole head to order a few objects | fixed: `path_order` opens only trees in the pack and takes the commit id instead of walking the history; `build_commit_members` builds only the touched folders (L3). Profile of a 5-file push on a 3,000-folder vault: `path_order` 13 ms, `build_commit_members` 62 ms | `b59aa14` |

## Medium

| Item | Done |
|---|---|
| F4 rewind ignored the selective clone | fixed: the same split as a merge, `not_written` reported |
| F5 folder→file (and file→folder) left the file off disk | fixed on every write path: deletions first (merge, rewind, read-only pull, history revert) |
| M2 lost `checkout.json` wedged commit and push on a pack clone | fixed: status, commit, pull and checkout rebuild the record from the tracked files on disk (one rule in `Vault__Checkout_Set.needs_rebuild/rebuild`; a pack clone is one with `packs_absorbed.json`); a loose sparse clone keeps the older blob rule |
| M1 / F8 pack-store handle closed under a reader | fixed: handles carry a reader count; only idle ones are evicted; 24 packs, 8 threads, 24,000 reads in the test |
| M5 pack clone walked every tree | fixed: skipped on a pack vault (not scoped); the working-copy step keeps the integrity check (every folder tree and blob local, else refuse) and counts the trees |
| M6 `history log` re-diffed absorbed commits after compaction | fixed: the log's provider fetches the archived commit indexes it reaches (one listing per folder, one batch read, kept locally, verified by the same rules); offline it walks as before. Found on the way: `archive/` holds both a snapshot and a commit index for a commit that was a snapshot's head, and the reader picked by commit id alone; it now opens each candidate until one is the kind asked |
| M3 compaction re-diffed the whole history for `file-commits` | fixed: starts from the previous verified local snapshot index, adds the absorbed commits' changes from their commit indexes; equals the full build (test) |
| M4 two requests per range | half fixed: one presigned URL per pack, renewed once if refused. `at`-first is deferred (below) |
| S1 `sgit fetch` with no path flipped a sparse clone to full | decided: `fetch` keeps 0.25.0's behaviour (every file written, clone stays sparse); only `checkout --all` makes it full; help text says so |
| S3 `sgit dump` misread index packs | fixed (one filter) |
| S4 index packs orphaned by a 0.25.0 compaction | fixed: compaction moves an index whose data pack sits in `archive/` to `indexes/archive/`, deletes one whose data pack is gone; `pack index verify` then reports no orphans |

## Low

| Item | Done |
|---|---|
| L1 / F7 unbounded inflate | fixed: 1 GiB cap, refuse past it |
| L2 `.`/`..`/separators in member names | fixed: dropped whole at parse time |
| F6 refused ranged member wedged a scoped clone | fixed: such a pack is not absorbed; a pull on a pack vault runs the pack fetch when the head's root tree is missing, or when the walk finds blobs the host has no loose copy of |
| F9 `pull --no-checkout` deletes on disk | kept and documented: an edited file blocks the pull; leaving the file would make the next commit put it back for everyone |
| F10 `packs()` cached None | fixed: re-probed after a second |
| F11 count vs lines | fixed: "… and N more (the newest 500 shown)" |
| F12 name-key collision | fixed: by file id |
| L5 SQLite where the dev pack said no database | noted in TM-R43 with the alternative |
| L4 index pack size (32.6 MB beside a 69 MB pack) | **deferred**: the optional member set for the cross-references is a format decision I would rather take with you (it changes what a reader expects to find); the numbers are in the CHANGELOG |
| M4 locate through `at` before the central directory | **deferred**: on the 76,000-file vault the snapshot index (32.6 MB) is larger than the directory a scoped clone reads (10.7 MB), and reading the index by ranges needs its header, which lists every member; this pays once Phase 4's server-side index answers a folder query |

## Evidence

- `tests/unit` + `tests/security`: **4,708 passed** (32 new tests across six files).
- `tests/integration` (3.12 venv, real `sgraph-ai-app-send` server): 75 passed, 1 skipped.
- Cross-version harness, the released `sgit-ai==0.25.0` and the branch build against the real test
  server, scenarios A/B/C re-run after the fixes: **ALL COMMANDS OK**, trees equal at every hop.
- Bandit against the baseline: no findings.

## What needs you

- The dev merge, when you want it (the `[Unreleased]` CHANGELOG section "Fixed — from the reviews of
  the pack-indexes branch" is the release note).
- L4: whether to move `blob-paths` and `file-commits` to an optional member set now or with Phase 4.
- The build agent's offer in its section 7 stands: M5 and M6 were where the newsroom's clones and logs
  gain; both are in.
