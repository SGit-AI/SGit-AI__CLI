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
