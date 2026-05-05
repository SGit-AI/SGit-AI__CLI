# B06 Dev Execution Brief — Layer Cleanup

**Date:** 2026-05-05
**Author:** Explorer reviewer agent (claude/cli-explorer-session-J3WqA)
**Purpose:** Precise implementation guide for the executor dev agent, derived from live codebase analysis.
**Base brief:** `team/villager/v0.13.x__brief-pack/brief__06__layer-cleanup.md`

This document supersedes the base brief for implementation purposes.
Read the base brief first for rationale; use this document for every file path, line number, and command.

---

## Baseline state

- **Tests:** 3,175 passing (unit), 128 in qa tier
- **KNOWN_VIOLATIONS:** 14 entries (7 non-dev, 7 dev-plugin)
- **Target after B06:** KNOWN_VIOLATIONS = 7 (all dev-plugin; the 7 architectural violations removed)

---

## Cleanup 1 — Move `Simple_Token` files to `sgit_ai/crypto/simple_token/`

### Why

`Vault__Crypto` imports `Simple_Token` inside two methods to check whether a vault key is a simple-token.
`Simple_Token` is a crypto primitive (HKDF-based key derivation from a word-token), not a network concern.
Moving it into `crypto/` makes the dependency direction correct and removes the sole crypto-layer violation.

### Files to create

```
sgit_ai/crypto/simple_token/__init__.py        (empty)
sgit_ai/crypto/simple_token/Simple_Token.py    (git mv from network/transfer/)
sgit_ai/crypto/simple_token/Simple_Token__Wordlist.py  (git mv from network/transfer/)
```

### Git commands

```bash
mkdir -p sgit_ai/crypto/simple_token
touch sgit_ai/crypto/simple_token/__init__.py
git mv sgit_ai/network/transfer/Simple_Token.py          sgit_ai/crypto/simple_token/Simple_Token.py
git mv sgit_ai/network/transfer/Simple_Token__Wordlist.py sgit_ai/crypto/simple_token/Simple_Token__Wordlist.py
```

### Import-path changes (old → new)

Every occurrence of:
```
sgit_ai.network.transfer.Simple_Token
sgit_ai.network.transfer.Simple_Token__Wordlist
```
must become:
```
sgit_ai.crypto.simple_token.Simple_Token
sgit_ai.crypto.simple_token.Simple_Token__Wordlist
```

### Full list of files to update (with line numbers)

| File | Lines | What changes |
|---|---|---|
| `sgit_ai/crypto/Vault__Crypto.py` | 100, 111 | inline import inside `parse_vault_key` and `simple_token_to_keys` |
| `sgit_ai/network/transfer/Vault__Transfer.py` | 15–16, 44 | top-level imports + one inline |
| `sgit_ai/network/transfer/Vault__Archive.py` | 90, 120 | inline imports inside two methods |
| `sgit_ai/cli/CLI__Publish.py` | 9–10 | top-level imports |
| `sgit_ai/cli/CLI__Create.py` | 23–24 | inline imports |
| `sgit_ai/cli/CLI__Export.py` | 9–10 | top-level imports |
| `sgit_ai/cli/CLI__Share.py` | — | no direct import (uses Vault__Transfer; no change needed here) |
| `sgit_ai/cli/CLI__Vault.py` | 30, 132–133, 542–543, 795, 1155–1156 | inline imports across 5 methods |
| `sgit_ai/cli/CLI__Main.py` | 758, 791, 814 | inline imports in 3 methods |
| `sgit_ai/workflow/clone/Step__Transfer__Init_Vault.py` | 13–14 | inline imports |
| `sgit_ai/workflow/clone/Step__Clone__Setup_Local_Config.py` | 18 | inline import |
| `sgit_ai/workflow/clone/Step__Clone__Headless__Setup_Config.py` | 19 | inline import |
| `sgit_ai/core/Vault__Sync.py` | 45 | inline import |
| `sgit_ai/core/Vault__Sync__Base.py` | 49 | inline import |
| `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` | 11, 249 | inline imports |
| `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` | 95 | inline import |

### Layer-import test

In `tests/unit/architecture/test_Layer_Imports.py` remove this line from `KNOWN_VIOLATIONS`:
```python
'sgit_ai/crypto/Vault__Crypto.py: imports sgit_ai.network.transfer.Simple_Token',
```

Also remove the module-level comment that references this violation (lines 15–18).

### Verification

After updating all imports, `Simple_Token` must **not** appear in any `grep` of `sgit_ai/network/` except possibly `Vault__Archive.py` if that file stays in `network/transfer/` (which it should — it's a network archive, not crypto).

```bash
grep -r "network.transfer.Simple_Token" sgit_ai/ --include="*.py"
# Expected: 0 results
```

---

## Cleanup 2 — Move `Vault__Transfer` to `sgit_ai/core/actions/transfer/`

### Why

`Vault__Transfer` (320 LOC) lives in `network/transfer/` but imports 6 storage-layer classes (`Vault__Object_Store`, `Vault__Ref_Manager`, `Vault__Commit`, `Vault__Storage`, `Vault__Sub_Tree`, `Vault__Branch_Manager`). Network files must not import storage. Moving to `core/actions/transfer/` eliminates all 6 violations.

### Git commands

```bash
mkdir -p sgit_ai/core/actions/transfer
touch sgit_ai/core/actions/transfer/__init__.py
git mv sgit_ai/network/transfer/Vault__Transfer.py sgit_ai/core/actions/transfer/Vault__Transfer.py
```

### Inside `Vault__Transfer.py` itself

After the move, update the two Simple_Token imports (from Cleanup 1):
```python
# lines 15–16 (before move):
from sgit_ai.network.transfer.Simple_Token           import Simple_Token
from sgit_ai.network.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist
# → becomes:
from sgit_ai.crypto.simple_token.Simple_Token           import Simple_Token
from sgit_ai.crypto.simple_token.Simple_Token__Wordlist import Simple_Token__Wordlist
```
The inline import at line 44 must also change to the new path.

The 6 storage imports (lines 10–14) are now legal from `core/`; no path change needed.

### Files that import `Vault__Transfer` (all must update their import path)

| File | Lines | Change |
|---|---|---|
| `sgit_ai/cli/CLI__Publish.py` | 8 | top-level import |
| `sgit_ai/cli/CLI__Share.py` | 12 | top-level import |
| `sgit_ai/cli/CLI__Export.py` | 8 | top-level import |
| `sgit_ai/cli/CLI__Vault.py` | 544 | inline import |
| `sgit_ai/workflow/clone/Step__Transfer__Receive.py` | 15 | inline import |

Old path: `sgit_ai.network.transfer.Vault__Transfer`
New path: `sgit_ai.core.actions.transfer.Vault__Transfer`

### Layer-import test

Remove all 6 `_VAULT_TRANSFER` entries from `KNOWN_VIOLATIONS` and delete the `_VAULT_TRANSFER` variable:

```python
# Delete these lines:
_VAULT_TRANSFER = 'sgit_ai/network/transfer/Vault__Transfer.py'
# ... and all 6 f-string entries in KNOWN_VIOLATIONS
```

### Verification

```bash
grep -r "network.transfer.Vault__Transfer" sgit_ai/ --include="*.py"
# Expected: 0 results

python -m pytest tests/unit/architecture/test_Layer_Imports.py -v
# Expected: all green, KNOWN_VIOLATIONS now 7 (dev-plugin only)
```

---

## Cleanup 3 — Extract `Vault__Graph_Walk`

### Why

BFS commit/tree/blob walk is duplicated in three places. After B04–B05, `Vault__Sync__Pull._fetch_missing_objects` still has a 170-LOC inline BFS, `Step__Clone__Walk_Trees` has a 56-LOC tree-only BFS, and `Step__Pull__Fetch_Missing` has a 78-LOC BFS. A single class removes ~200 LOC net and prevents a fourth copy when B08 lands.

### New file

`sgit_ai/storage/graph/Vault__Graph_Walk.py`

Create `sgit_ai/storage/graph/__init__.py` (empty).

#### Class specification

```python
"""BFS walk of the commit/tree/blob DAG for a vault."""
from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.storage.Vault__Commit            import Vault__Commit
from sgit_ai.storage.Vault__Object_Store      import Vault__Object_Store

class Vault__Graph_Walk(Type_Safe):
    vc            : Vault__Commit       = None
    obj_store     : Vault__Object_Store = None
    read_key      : bytes               = None
    stop_at       : list                = None   # commit IDs; BFS stops at these
    include_blobs : bool                = True

    def walk(self, start_commit_ids: list) -> dict:
        """BFS from start_commit_ids through commits → trees → blobs.

        Returns dict(n_commits, n_trees, n_blobs, missing_commit_ids,
                     missing_tree_ids, missing_blob_fids).
        Callbacks and progress are intentionally excluded from the class
        — callers wrap the return dict and emit progress themselves.
        """
```

**Return dict shape:**
```python
{
    'n_commits'         : int,         # commits visited (excluding stop_at)
    'n_trees'           : int,         # unique trees encountered
    'n_blobs'           : int,         # unique blobs encountered
    'missing_commit_ids': list[str],   # commits absent from obj_store
    'missing_tree_ids'  : list[str],   # trees absent from obj_store
    'missing_blob_fids' : list[tuple], # (fid, is_large) pairs for absent blobs
}
```

**BFS algorithm (3-phase, mirrors existing implementations):**

Phase 1 — commits:
- BFS from `start_commit_ids`, skipping any ID in `stop_at` or already in `visited_commits`
- Any commit not in `obj_store` → add to `missing_commit_ids`
- Load each commit that IS present, collect its `tree_id` and `parents`

Phase 2 — trees:
- BFS from collected root `tree_id`s
- Any tree not in `obj_store` → add to `missing_tree_ids`
- Load each present tree, collect sub-tree IDs

Phase 3 — blobs (only if `include_blobs=True`):
- Iterate `seen_trees`, load each tree, collect blob entries
- Any blob not in `obj_store` → add to `missing_blob_fids` as `(f'bare/data/{blob_id}', is_large)`

The class does **not** download anything — callers batch-download using the returned missing-ID lists.

#### Refactoring the three call sites

**`Step__Clone__Walk_Trees.py`** — currently only walks trees (commits already walked upstream by `Step__Clone__Walk_Commits`). Keep it as-is; it reads `root_tree_ids` from state and downloads them. This step is narrow enough to not need `Vault__Graph_Walk` — it just uses `batch_read` directly. **Do not refactor this step.**

**`Step__Pull__Fetch_Missing.py`** — this step receives `named_commit_id` and `clone_commit_id` from prior steps and downloads everything missing. Refactor `execute()` to:
1. Construct `Vault__Graph_Walk(vc=..., obj_store=..., read_key=..., stop_at=[clone_commit_id], include_blobs=True)`
2. Call `result = gw.walk([named_commit_id])`
3. Batch-download `result['missing_commit_ids']`, `result['missing_tree_ids']`, then blobs
4. Update `n_objects_fetched` in state

**`Vault__Sync__Pull._fetch_missing_objects`** — refactor to delegate the graph-walk phase to `Vault__Graph_Walk`, then use its return dict for the download phases. The timing / progress emission stays in this method. Existing callers and return dict shape must not change.

### Tests

New test file: `tests/unit/storage/graph/test_Vault__Graph_Walk.py`

Minimum 6 tests (no mocks — use `Vault__API__In_Memory` + real vault fixtures):

| Test | What it verifies |
|---|---|
| `test_walk_single_commit` | 1 commit → 1 tree → 1 blob; counts correct |
| `test_walk_stop_at_excludes_ancestor` | stop_at excludes older commits from results |
| `test_walk_missing_commit` | commit absent from obj_store appears in `missing_commit_ids` |
| `test_walk_missing_tree` | tree absent appears in `missing_tree_ids` |
| `test_walk_missing_blob` | blob absent appears in `missing_blob_fids` |
| `test_walk_include_blobs_false` | `include_blobs=False` → `missing_blob_fids` is empty |

Existing tests for the 3 call sites must all pass without modification.

---

## Commit sequence

Do these as **3 separate commits**, one per cleanup, each with passing tests:

1. `Cleanup 1 (B06): move Simple_Token/* to crypto/simple_token/, update 16 call sites`
2. `Cleanup 2 (B06): move Vault__Transfer to core/actions/transfer/, update 5 callers`
3. `Cleanup 3 (B06): extract Vault__Graph_Walk, refactor Step__Pull__Fetch_Missing + Vault__Sync__Pull`

---

## Acceptance checklist

- [ ] `sgit_ai/crypto/simple_token/Simple_Token.py` exists (git-mv'd)
- [ ] `sgit_ai/crypto/simple_token/Simple_Token__Wordlist.py` exists (git-mv'd)
- [ ] `sgit_ai/core/actions/transfer/Vault__Transfer.py` exists (git-mv'd)
- [ ] `sgit_ai/storage/graph/Vault__Graph_Walk.py` exists (new)
- [ ] `grep -r "network.transfer.Simple_Token" sgit_ai/` → 0 results
- [ ] `grep -r "network.transfer.Vault__Transfer" sgit_ai/` → 0 results
- [ ] `KNOWN_VIOLATIONS` shrunk from 14 → 7 (dev-plugin entries only)
- [ ] `test_Layer_Imports.py` green
- [ ] `test_Vault__Graph_Walk.py` has ≥ 6 tests, all green
- [ ] All existing tests pass: `pytest tests/unit/ -q` ≥ 3,175 passing
- [ ] No new mocks / monkeypatches introduced

---

## Notes for the reviewer

After B06 lands, verify:
1. `KNOWN_VIOLATIONS` is exactly the 7 dev-plugin entries (no more, no fewer).
2. `Vault__Archive.py` still compiles — it stays in `network/transfer/` but its `Simple_Token` imports now point to `crypto/simple_token/`.
3. `Step__Clone__Walk_Trees.py` was **not** changed (brief says leave it alone).
4. `_fetch_missing_objects` return dict is **unchanged** (same keys, same semantics).
