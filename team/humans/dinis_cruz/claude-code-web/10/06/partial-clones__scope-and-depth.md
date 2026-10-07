# Partial clones — a folder scope and a history depth (6 Oct 2026)

**Branch:** `claude/charming-babbage-5hzcxq` · **Vault measured:** `y8pwtjlw` (626 commits, 8,013+ trees, 9,404 blobs, 18,720 objects at HEAD time)
**Ask:** agents that know which folders they read and write should be able to clone just those,
read *and* write; plus a shallow (no-history) mode; and none of it may change the full clone.

## 1. The idea, in one paragraph

The vault is a Merkle tree: a commit names a root tree, a tree names its children by id. To
hold `mail/crm.riskmandate/` a clone needs the root tree, the `mail/` tree (the *spine*) and
the folder's own subtree; everything else is an entry it keeps by id ("opaque"). To commit a
change inside the folder, rebuild the folder's subtree from disk, then each tree on the spine
with one entry replaced, and keep the siblings' ids — exactly what the whole-vault builder
would produce, byte for byte, because tree encryption is deterministic (a test proves the
rebuilt root id equals the full builder's). Push uploads the new commit, the spine trees, the
changed subtree and the new blobs; the server needs nothing new. Two scoped clones in
different folders cannot conflict: out-of-scope entries are always the remote's, by id.

## 2. What was built

| piece | where |
|---|---|
| scope model (paths + boundaries, pure path logic) | `storage/Vault__Scope.py` (re-exported from `core/scope/`) |
| opaque entries in the tree builder (`build`, `build_from_flat`, `opaque=`), canonical entry order | `storage/Vault__Sub_Tree.py` |
| scoped flatten → (flat, opaque); level-by-level fetch walk that only opens held + spine folders | `storage/Vault__Scoped_Tree.py` |
| local config: `scope_paths`, `shallow_boundaries` (empty on full clones) | `schemas/Schema__Local_Config.py` |
| clone: `--depth N`, `--path F` (repeatable); depth-limited commit walk records boundaries; scoped tree walk; scoped checkout; bulk sweep skipped for partial clones | clone steps, `Vault__Sync__Clone`, `CLI__Main`/`CLI__Vault` |
| commit / write_file: scoped flatten + opaque rebuild; writes outside scope refused with the path | `Vault__Sync__Commit` |
| status: scoped diff; chain fetch stops at boundaries | `Vault__Sync__Status` |
| pull: scoped fetch (held folders only), merge within scope with theirs' opaque entries, commit walk stops at boundaries (push's implicit pull used to deepen a shallow clone to the root) | `Step__Pull__Fetch_Missing`, `Step__Pull__Merge`, `Vault__Sync__Pull` |
| push: scoped flatten, trees/blobs the clone never fetched are skipped (unchanged, on the server), cache reconcile skipped | `Vault__Sync__Push`, `Vault__Batch` |
| widen (`sgit fetch <folder>`), unshallow (`sgit fetch --unshallow`), `require_whole` | `core/actions/scope/Vault__Sync__Scope.py` |
| guard on `check fsck`, `dump`, `publish`, `vault move` | `cli/CLI__Scope_Guard.py` |
| branch switch keeps scope fields | `Vault__Branch_Switch` |

## 3. Numbers on the real vault (this session, through its egress gateway)

| clone | objects | store | files | wall |
|---|---|---|---|---|
| full (bulk sweep, unchanged) | 18,720 | 173 MB | 3,442 | 81 s |
| `--path mail/crm.riskmandate --depth 1` | 429 | 3.2 MB | 365 | **14 s** |
| `--path docs --path conductor --depth 1` | 20 | — | 15 | **5 s** |
| widen the CRM clone with `docs` | +10 | — | +8 | 2 s |

On the scoped clone: `status` in sync; `history log` shows HEAD and stops; `check fsck`
refuses naming what the clone holds and how to widen.

## 4. "No side effects on the full clone" — how that was held

- Every scope branch is behind `scope.is_scoped()` / `is_partial()`; a whole-vault clone takes
  the exact calls it took before (`flatten`, `build`, `build_from_flat`, `_fetch_missing_objects`
  without the new kwarg, `checkout`). The existing pull-step tests use a fake sync client with
  no crypto and no new kwargs, and they pass unchanged — which is the proof the full path is
  not touched.
- `Vault__Sub_Tree.build*` with no opaque entries runs the old code; with them, the entry
  order is re-established to files-then-folders by name so ids match the whole-vault builder.
- Real vault, before and after: a full clone gives the same 18,720 objects, empty scope and
  boundary in its config, and `fsck` reports the same 41 missing objects.
- `pytest tests/unit/ -n auto`: 3,932 passed (21 new partial-clone tests on two real clones
  in the in-memory API: read, write, delete, refuse-outside-scope, write_file, fast-forward
  and three-way pulls with changes outside scope, two scoped agents never conflicting, dirty
  edit survives a pull, depth-1 round trips, unshallow, scoped+shallow, widen, guards, branch
  switch, and a full-clone-unchanged check; 8 storage tests on the scoped tree).

## 5. Caveats and follow-ups

- A folder renamed by another agent silently leaves a clone's scope (names are decrypted
  along the spine). Pull should notice a held path vanishing and say so. Not done.
- Scoped clones cannot see blobs missing elsewhere; the push fix from earlier today should ship
  with this (same branch).
- `history log` on a shallow clone ends with "history stops here: shallow clone … sgit fetch
  --unshallow" instead of an `[object not found locally]` line.
- A shared, immutable object cache across clones on one machine would make every agent's
  clone after the first a local copy — the browser-style cache idea; separate change.
- `clone-branch` (thin) still walks all commits serially; with `--depth 1` on `sgit clone`
  there is little reason left to use it.

## 6. Deep review before the PR to main (same day, evening)

Two passes over `origin/main...origin/dev` after the merge: a code review (bugs, side effects)
and a security review (new exploitable issues only, >80 % confidence). CI on dev was green
first (run 37544894784 on ddee8a4).

### Security review — no new vulnerability; three hardening gaps closed

No high-confidence exploitable issue was introduced. Three pre-existing "trust the host /
trust the committer" gaps that the new fetch paths exercise more were closed anyway:

| Gap | Fix | Test |
|---|---|---|
| A batch read wrote whatever `file_id` the host answered with, and the id names the on-disk path | `_batch_read_chunk` keeps only requested ids | `Test_API__Ignores_Unrequested_File_Ids` (real local HTTP server answering with `local/config.json` and an extra object) |
| `Vault__Verified_Write.save` accepted any contained path (`local/config.json`, a working-copy file) | store-leaf allow-list `STORE_FILE_ID` + protected-dir check, before the content-address check | `Test_Verified_Write__Store_Paths_Only` |
| Pull let an untracked file be overwritten when the tree entry's `content_hash` CLAIMED the same content | proven from the decrypted blob (`blob_hash_fn`), the claim is ignored | `test_commit_whose_entry_hash_lies_cannot_overwrite_an_untracked_file` (a commit built with a lying hash) |

### Code review — 15 findings, what changed

| # | Finding | Resolution |
|---|---|---|
| 1 | `Vault__Head_Paths` flattened the whole tree on a scoped clone → tracked-wins rule broke, a tracked file under an ignored dir was dropped by the next commit | scoped flatten; test |
| 2 | read-only scoped clones: status/checkout used the whole tree | scoped in `_status_read_only` and the RO checkout step; test |
| 3 | sparse push could try to load a blob it never fetched | collector skips any blob not local |
| 4 | `sgit ls`/`fetch`/`cat` on a scoped clone walked a sibling's tree and failed | `_get_head_flat_map` scoped; test |
| 5 | other commands crash with "vault may be corrupted — run fsck" on a partial clone | friendly error naming the scope + how to widen (generic, for every command); test |
| 6 | branch-only push re-uploaded the whole clone-branch history each time | stops at the server's clone head; blobs the server has are not re-sent — and the ref CAS was matching the LOCAL ref bytes, so the ref write conflicted on every push after a commit (silent on the in-memory API, a 409 on the real one): now matches the server's bytes; test checks the server ref and that nothing re-sent is a blob |
| 7 | status walked the whole local history on every call | walk stops at known-complete heads; test (0 object reads when up to date; N when N behind); the truncated-fetch case is covered by the existing lower-bound test |
| 8 | widen overwrote files already on disk under the new folder | refuses naming the clash; held folders untouched; test |
| 9 | one failing bulk-sweep chunk aborted the clone | fail-soft per chunk; test |
| 10 | sweep counters unsynchronised across threads | lock + summed futures |
| 11 | duplicate parents counted against the fetch limit | deduped |
| 12 | `CLI__Scope_Guard` duplicated `require_whole` | delegates |
| 13 | pull-step call shape | kept (the fake-client tests prove the full path is unchanged) |
| 14 | guard re-read the config | config read once in the merge step, passed through |
| 15 | `Vault__Scope` held raw `list[str]` | `Safe_Str__File_Path` / `Safe_Str__Commit_Id` with validation (`..`, absolute, non-object ids refused; nested folders collapse) |

### What the new tests then found (would have shipped otherwise)

- **Typed boundary ids broke unshallow and the status boundary stop.** `Safe_Str` hashes
  differently from the equal `str` (`'x' in {Safe_Str('x')}` is False) and `os.path.join`
  sanitises it (`/` → `_`), so once the config fields became Safe types the boundary commit
  was "not in the local store" and `--unshallow` on a scoped shallow clone fetched nothing.
  `Vault__Scope.boundary_ids()` / `folders()` hand consumers plain strings; a test pins both
  behaviours. Worth remembering for every Safe_Str that reaches a path or a set.
- The first status rewrite assumed "a local commit has local ancestors", which a truncated
  fetch (limit hit) violates; the walk now stops only at known-complete heads.
- Branch-only push's ref CAS bug above (pre-existing, invisible to the in-memory API).

`pytest tests/unit/ -n auto`: 3,953 passed (21 new review tests under `tests/unit/review/`).

### Follow-up (7 Oct): the merge of main into dev and a CI flake that was a real leak

Merging `main` into `dev` for PR #7 conflicted only on the release bot's version bumps
(dev v0.17.3, main v0.17.0; dev kept). CI on that merge then failed on
`test_Dev__Tree__Graph__Happy::test_analyse_temp_dir_cleaned_up`, which diffed `/tmp` before
and after `analyse()` and so could see any vault another xdist worker was creating at that
moment. Rewriting it to watch the `mkdtemp` calls made inside the call exposed something real:
every `sgit clone` (all five entry points) creates `/tmp/sgit-clone-*` as the workflow
workspace's root, the runner removes the workspace inside it on success, and the root stays —
one empty dir per clone, 3,881 of them in this sandbox. `_run_clone_workflow` now removes the
root in its `finally`, success or failure; a review test clones three ways and checks none of
the roots survive.
