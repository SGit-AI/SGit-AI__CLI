# Pack indexes: steps 1 to 5 shipped on the branch (26 Oct 2026)

**Branch:** `claude/charming-babbage-5hzcxq`, seven commits on top of what went into 0.25.0, not on `dev`.
**Plan followed:** section 7 of `review__pack-indexes-dev-pack.md` (steps 1–5); step 6 (Phase 4, with the
SG/Vault team) is not started. Every step has its CHANGELOG entry under `[Unreleased]`, its threat-model row
(TM-R41 note, TM-R42 extended, TM-R43 new) and its tests; `tests/unit` + `tests/security` is at 4,677 passing.

| Step | Commit | What |
|---|---|---|
| 1 | `00b5461` | the index writer: an index pack beside every data pack (signed header, encrypted members), `pack index build / verify / stats`, gaps |
| 2 | `f102ebd` | the reader: index packs fetched with their data packs; the pull's fetch plan, the new head's flat map and the first flat map after a clone from the indexes; `history log` from `changes` |
| 2b | `125dbe3` | the flat map assembled incrementally (18.6 s → 3.4 s on the 228k-file vault) |
| 3 | `35ba8a9` | the selective working copy: `clone --no-checkout`, `pull --no-checkout`, `sgit checkout <path> / --since-pull / --changed-since / --all`, the checkout set, the status line |
| 4 | `3153802` | the pack store: `clone --pack-store` keeps packs in place and reads objects by offset (SQLite table), verify at intake and on read, compaction swap, `pack store status / extract / rebuild` |
| 5 | `f3485fd` | path-ordered packs, `at` / `tree_at` in the index, scoped clones and pulls by byte ranges, `Vault__API.read_range` |

## Numbers (228,000 files / 38,000 folders, in-memory host, warm disk)

| | before | after |
|---|---|---|
| pull that brings a 300-file pass | 31.7 s | 16.9 s (plan from the indexes: 172 trees, 300 blobs, none walked) |
| `history log` 10 commits with counts | 5.7 s | 0.2 s |
| flat map of an unseen head | 6.4 s (walk, warm; 45 s cold at the newsroom) | 3.4 s from the indexes |
| first `status` after a clone | 8.2 s | 8.4 s (unchanged) |
| full clone, loose | 216 s | 216 s (the time is the extraction and the checkout) |
| full clone, `--pack-store` | — | 177 s (the 14 packs land in 4.4 s and 8 requests; the rest is writing the 228,000-file working copy; `.sg_vault` is 398 MB: packs 250, snapshot index 52, table 78) |
| `pack index build --all` (backfill) | — | 178 s for 14 index packs |

The snapshot index of that vault is 52.5 MB with 77,742 members (the folder members for every folder, the
cross-references, the commit graph), against a 180 MB snapshot pack: every clone downloads it. The format is
the dev pack's; the folder members are what Phase 2's `at` lives in. If the size matters before Phase 4, the
cross-references (`blob-paths`, `file-commits`, about a third) can move to an optional member set.

## Decisions I took alone, worth a look

1. **A lying index below the root.** The reader anchors an index's flat map to the head's root tree (one
   tree read); a lie below the root in a *signed* index reaches the working copy with the standing of a commit
   signed by that key, and `pack index verify` finds it. Documented in TM-R42 with a `Known_Gaps` test. The
   alternative, verifying every folder against its tree, is the walk the index exists to avoid.
2. **`sgit checkout <path>` is the file verb**; `sgit branch checkout <target>` keeps switching branches. Rule 9
   put the daily verb at the top level; the name collides with git's "checkout a branch" only in spirit.
3. **A plain `pull` on a selective clone writes only the changed files it has checked out** and reports the
   rest ("N changed file(s) not written … `sgit checkout --since-pull`"). `pull --no-checkout` writes nothing.
   A full clone refuses `--no-checkout` (it would leave the working copy behind the head).
4. **The checkout set is a plain file** (`local/checkout.json`, the paths held; `last-pull.json` beside it),
   under the TM-R41 boundary like the flat and scan caches. A sparse clone from before the record keeps the old
   rule (blob fetched = checked out), which pack vaults cannot use because their packs bring every blob.
5. **The pack store verifies on every read**, not only at intake (the dev pack said "first read, remembered"):
   a hash per read is cheap next to the disk, and it makes T9's flipped byte a certainty. The table holds pack,
   object id, offset, length: content addresses and numbers, nothing named.
6. **The scoped reader locates objects through each pack's central directory** (two ranged reads per pack,
   cached), not through `at`: the directory covers commits, older versions and unchanged files in older packs,
   which `at` in the head's folder members does not. `at` is written (and verified) for Phase 4's `sgit cat`,
   where the index alone must answer. A host without the presigned route falls back to whole packs and says so.
7. **Path order is on by default** for every pack written, since 0.24.0–0.25.0 extract any order; what the host
   newly learns (which members sit together) is in TM-R42.
8. **Two pushes in one second give pack names that sort by commit id**, so "the last listed pack is the newest"
   is false; three tests assumed it and were fixed to pick by commit. Nothing in the client relies on it
   (`sync_down` chooses snapshots by the head), but it is worth knowing when reading listings.

## What needs you

- A dev merge when you want it (I have not merged); a release note draft is the `[Unreleased]` section.
- Phase 4 (`sgit cat <vault> <path>` with no clone; the presigned range on the live API) with the SG/Vault
  team: the pieces are here (`at`, `read_range`, the index reader), the command and its auth are not.
- `/tmp` on this machine holds 13,600 `sgit-*` folders left by test runs (not mine to delete: the cleanup was
  refused); the disk filled once during a measurement. A `tests/unit/conftest.py` fixture that removes a
  test's own vault folders at teardown would stop it growing.
