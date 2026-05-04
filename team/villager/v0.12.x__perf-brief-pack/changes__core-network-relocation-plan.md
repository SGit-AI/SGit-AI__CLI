# Architect Relocation Plan — B13 Core + Network

**Produced by:** Villager Architect (B13)
**Status:** Approved by Dinis — executing
**Date:** 2026-05-04
**Prerequisites:** B12 complete (storage layer extracted, layer-import test green)

---

## Design decisions (Dinis-approved)

| # | Decision | Choice |
|---|---|---|
| 1 | `Vault__Sync.py` fate | **Delete outright** after all sub-classes extracted — no shim layer kept |
| 2 | Network layout | **Sub-folders:** `network/api/` + `network/transfer/` |
| 3 | Remaining `sync/` files | **Move to `core/`** with grouped sub-folders — no files left in `sync/` |

---

## Phase 2 — Core layer (`sgit_ai/core/`)

### 2a — 12 Vault__Sync__* sub-classes → core/actions/<command>/

| Current path | New path |
|---|---|
| `sgit_ai/sync/Vault__Sync__Base.py` | `sgit_ai/core/Vault__Sync__Base.py` |
| `sgit_ai/sync/Vault__Sync__Admin.py` | `sgit_ai/core/actions/admin/Vault__Sync__Admin.py` |
| `sgit_ai/sync/Vault__Sync__Branch_Ops.py` | `sgit_ai/core/actions/branch/Vault__Sync__Branch_Ops.py` |
| `sgit_ai/sync/Vault__Sync__Clone.py` | `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` |
| `sgit_ai/sync/Vault__Sync__Commit.py` | `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` |
| `sgit_ai/sync/Vault__Sync__Fsck.py` | `sgit_ai/core/actions/fsck/Vault__Sync__Fsck.py` |
| `sgit_ai/sync/Vault__Sync__GC_Ops.py` | `sgit_ai/core/actions/gc/Vault__Sync__GC_Ops.py` |
| `sgit_ai/sync/Vault__Sync__Lifecycle.py` | `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` |
| `sgit_ai/sync/Vault__Sync__Pull.py` | `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` |
| `sgit_ai/sync/Vault__Sync__Push.py` | `sgit_ai/core/actions/push/Vault__Sync__Push.py` |
| `sgit_ai/sync/Vault__Sync__Sparse.py` | `sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py` |
| `sgit_ai/sync/Vault__Sync__Status.py` | `sgit_ai/core/actions/status/Vault__Sync__Status.py` |
| `sgit_ai/sync/Vault__Sync.py` (facade) | **Deleted** after all subs extracted |

### 2b — 17 remaining sync/ files → core/ root + actions sub-folders

**`core/` root** (7 shared/infrastructure files — used by multiple actions):

| Current path | New path | Why root (not a sub-folder) |
|---|---|---|
| `sgit_ai/sync/Vault__Bare.py` | `sgit_ai/core/Vault__Bare.py` | Used by CLI__Vault directly; init/clone both use it |
| `sgit_ai/sync/Vault__Components.py` | `sgit_ai/core/Vault__Components.py` | Used by Diff, Branch_Switch, Revert, Sync__Base |
| `sgit_ai/sync/Vault__Context.py` | `sgit_ai/core/Vault__Context.py` | Cross-cutting: detects cwd vault state |
| `sgit_ai/sync/Vault__Errors.py` | `sgit_ai/core/Vault__Errors.py` | Typed exceptions used across all actions |
| `sgit_ai/sync/Vault__Ignore.py` | `sgit_ai/core/Vault__Ignore.py` | Ignore rules used by commit, status, diff |
| `sgit_ai/sync/Vault__Remote_Manager.py` | `sgit_ai/core/Vault__Remote_Manager.py` | Remote config, shared by fetch/push/pull |

**`core/actions/` sub-folders** (10 files across 10 actions):

| Current path | New path | Co-located with |
|---|---|---|
| `sgit_ai/sync/Vault__Branch_Switch.py` | `sgit_ai/core/actions/branch/Vault__Branch_Switch.py` | `Vault__Sync__Branch_Ops` |
| `sgit_ai/sync/Vault__Diff.py` | `sgit_ai/core/actions/diff/Vault__Diff.py` | — |
| `sgit_ai/sync/Vault__Dump_Diff.py` | `sgit_ai/core/actions/diff/Vault__Dump_Diff.py` | `Vault__Diff` |
| `sgit_ai/sync/Vault__Dump.py` | `sgit_ai/core/actions/dump/Vault__Dump.py` | — |
| `sgit_ai/sync/Vault__Fetch.py` | `sgit_ai/core/actions/fetch/Vault__Fetch.py` | — |
| `sgit_ai/sync/Vault__GC.py` | `sgit_ai/core/actions/gc/Vault__GC.py` | `Vault__Sync__GC_Ops`, `Vault__Change_Pack` |
| `sgit_ai/sync/Vault__Change_Pack.py` | `sgit_ai/core/actions/gc/Vault__Change_Pack.py` | `Vault__Sync__GC_Ops`, `Vault__GC` |
| `sgit_ai/sync/Vault__Batch.py` | `sgit_ai/core/actions/push/Vault__Batch.py` | `Vault__Sync__Push` |
| `sgit_ai/sync/Vault__Merge.py` | `sgit_ai/core/actions/merge/Vault__Merge.py` | — |
| `sgit_ai/sync/Vault__Revert.py` | `sgit_ai/core/actions/revert/Vault__Revert.py` | — |
| `sgit_ai/sync/Vault__Stash.py` | `sgit_ai/core/actions/stash/Vault__Stash.py` | — |

**Final `core/` tree (after all moves):**

```
sgit_ai/core/
├── __init__.py
├── Vault__Sync__Base.py          (shared base for all Sync__* actions)
├── Vault__Bare.py
├── Vault__Components.py
├── Vault__Context.py
├── Vault__Errors.py
├── Vault__Ignore.py
├── Vault__Remote_Manager.py
└── actions/
    ├── admin/      Vault__Sync__Admin.py
    ├── branch/     Vault__Sync__Branch_Ops.py, Vault__Branch_Switch.py
    ├── clone/      Vault__Sync__Clone.py
    ├── commit/     Vault__Sync__Commit.py
    ├── diff/       Vault__Diff.py, Vault__Dump_Diff.py
    ├── dump/       Vault__Dump.py
    ├── fetch/      Vault__Fetch.py
    ├── fsck/       Vault__Sync__Fsck.py
    ├── gc/         Vault__Sync__GC_Ops.py, Vault__GC.py, Vault__Change_Pack.py
    ├── lifecycle/  Vault__Sync__Lifecycle.py
    ├── merge/      Vault__Merge.py
    ├── pull/       Vault__Sync__Pull.py
    ├── push/       Vault__Sync__Push.py, Vault__Batch.py
    ├── revert/     Vault__Revert.py
    ├── sparse/     Vault__Sync__Sparse.py
    ├── stash/      Vault__Stash.py
    └── status/     Vault__Sync__Status.py
```

After these moves, `sgit_ai/sync/` contains **zero files** and is deleted.

---

## Phase 3 — Network layer (`sgit_ai/network/`)

Current `api/` (7 files) → `sgit_ai/network/api/`:

| Current path | New path |
|---|---|
| `sgit_ai/api/API__Transfer.py` | `sgit_ai/network/api/API__Transfer.py` |
| `sgit_ai/api/Transfer__Envelope.py` | `sgit_ai/network/api/Transfer__Envelope.py` |
| `sgit_ai/api/Vault__API.py` | `sgit_ai/network/api/Vault__API.py` |
| `sgit_ai/api/Vault__API__In_Memory.py` | `sgit_ai/network/api/Vault__API__In_Memory.py` |
| `sgit_ai/api/Vault__Backend.py` | `sgit_ai/network/api/Vault__Backend.py` |
| `sgit_ai/api/Vault__Backend__API.py` | `sgit_ai/network/api/Vault__Backend__API.py` |
| `sgit_ai/api/Vault__Backend__Local.py` | `sgit_ai/network/api/Vault__Backend__Local.py` |

Current `transfer/` (4 files) → `sgit_ai/network/transfer/`:

| Current path | New path |
|---|---|
| `sgit_ai/transfer/Simple_Token.py` | `sgit_ai/network/transfer/Simple_Token.py` |
| `sgit_ai/transfer/Simple_Token__Wordlist.py` | `sgit_ai/network/transfer/Simple_Token__Wordlist.py` |
| `sgit_ai/transfer/Vault__Archive.py` | `sgit_ai/network/transfer/Vault__Archive.py` |
| `sgit_ai/transfer/Vault__Transfer.py` | `sgit_ai/network/transfer/Vault__Transfer.py` |

After these moves, `sgit_ai/api/` and `sgit_ai/transfer/` are deleted.

---

## Phase 4 — PKI fold (`sgit_ai/crypto/pki/`)

| Current path | New path |
|---|---|
| `sgit_ai/pki/PKI__Key_Store.py` | `sgit_ai/crypto/pki/PKI__Key_Store.py` |
| `sgit_ai/pki/PKI__Keyring.py` | `sgit_ai/crypto/pki/PKI__Keyring.py` |

After these moves, `sgit_ai/pki/` is deleted.

---

## Phase 5 — Layer-import test extension

`tests/unit/architecture/test_Layer_Imports.py` extended with:
- `network/` imports only `crypto/`, `safe_types/`, `schemas/`
- `core/` imports only `crypto/`, `storage/`, `network/`, `workflow/`, `safe_types/`, `schemas/`, `secrets/`
- `crypto/` pre-existing violation (`Vault__Crypto` → `transfer.Simple_Token`) cleared now that `transfer/` moves to `network/`

---

## Commit plan

| # | Commit | Scope |
|---|---|---|
| 1 | `B13: add sgit_ai/core/ skeleton` | Create `core/__init__.py` + `core/actions/` dirs |
| 2 | `B13: move Vault__Sync__Base to core/` | Base class first (others depend on it) |
| 3 | `B13: move lightweight Sync sub-classes` | admin, fsck, lifecycle, sparse, status |
| 4 | `B13: move branch sub-classes` | branch/ + Branch_Switch.py |
| 5 | `B13: move commit sub-class` | commit/ + Vault__Sync__Commit |
| 6 | `B13: move gc sub-classes` | gc/ + GC_Ops, GC, Change_Pack |
| 7 | `B13: move pull, push sub-classes` | pull/ + push/ + Vault__Batch |
| 8 | `B13: move clone sub-class` | clone/ |
| 9 | `B13: move remaining sync/ action files` | diff, dump, fetch, merge, revert, stash |
| 10 | `B13: move sync/ shared files to core/ root` | Bare, Components, Context, Errors, Ignore, Remote_Manager |
| 11 | `B13: delete Vault__Sync.py and sync/ directory` | Delete facade + directory |
| 12 | `B13: add sgit_ai/network/; move api/ + transfer/` | network/api/, network/transfer/ |
| 13 | `B13: fold pki/ into crypto/pki/` | pki → crypto/pki |
| 14 | `B13: extend layer-import enforcement test` | All 5 layers |

---

## Risk notes

- `Vault__Sync__Base.py` must move first — all 12 sub-classes import from it.
- `Vault__Sync.py` (the facade) imports all 12 sub-classes; delete last, after all subs moved.
- `Vault__Crypto.py` → `transfer.Simple_Token` pre-existing violation: after Phase 3 the path becomes `network.transfer.Simple_Token`. Update the known-violations entry in the test.
- ~130 files across `sgit_ai/` + `tests/` will have import path updates. All mechanical.
- The `workflow/clone/` directory (`Workflow__Clone` + step classes) stays under `workflow/` — it's the workflow framework layer, not `core/`. Brief B13 does not move it.
