# Push: Named-Branch Contamination Fix

**Date**: 2026-04-15  
**Branch**: `claude/cli-explorer-session-J3WqA`  
**Files changed**: `sgit_ai/sync/Vault__Sync.py`, `tests/unit/sync/test_Vault__Sync__Push.py`

---

## Problem: What Was Happening

### The Two-Branch Model (background)

Every SGit vault has two kinds of branches:

| Branch | Who uses it | Purpose |
|--------|-------------|---------|
| **Clone branch** (e.g. `local`) | Private to each user | Tracks the user's working state, including pull-merge commits |
| **Named branch** (e.g. `current`) | Shared / server-synced | The canonical vault snapshot visible to all collaborators |

When a user runs `sgit pull`, a **"Merge X into Y" commit** is created on the clone branch to integrate incoming server changes. This commit has two parents: the user's previous clone HEAD and the incoming named-branch HEAD.

These merge commits are **internal plumbing** — they should never appear on the shared named branch.

### The Bug

`Vault__Sync.push()` called `pull()` internally as a "fetch-first" safety step:

```
push():
  1. call pull()   ← creates "Merge current into local" on clone branch
  2. re-read clone HEAD  ← now points to the merge commit!
  3. set named branch ref = clone HEAD  ← BUG: named branch now points to a merge commit
```

**Result in `sgit log --graph`:**

```
*   obj-cas-imm-20bc19e1a72b  Merge current into local       ← clone lane
|\
| * 4c10a900b081  Merge current into local   ← WRONG: this should never be here
|/
* obj-cas-imm-13ffabedea2d  Merge current into local
...
```

`4c10a900b081 "Merge current into local"` appeared in the **right lane** (named branch), which is semantically wrong. This commit is a clone-branch artifact that leaked onto the shared named branch.

### Contamination Chain

Once a merge commit appears on the named branch:

1. User B does `sgit pull` → fetches the named branch → gets the merge commit as parent of their next merge
2. User B's graph now shows the merge commit in the **right lane**
3. Every subsequent pull/push compounds the contamination

---

## Fix: What Changed

### Core Approach

Instead of setting the named branch ref directly to `clone_commit_id` (which may be a merge commit after the internal pull), `push()` now **creates a clean new commit** for the named branch:

```python
push_target_id = vault_commit.create_commit(
    read_key   = read_key,
    tree_id    = str(clone_commit.tree_id),   # same files
    parent_ids = [named_commit_id] if named_commit_id else [],  # clean lineage
    message    = push_message,                 # user's last commit message
    branch_id  = str(named_meta.branch_id) if named_meta.branch_id else '',
)
```

This commit has:
- **Same file tree** as the clone HEAD (correct vault state)
- **Single parent** = current named branch HEAD (clean, linear history)
- **No pull-merge parents** (contamination impossible)

### Helper: `_find_user_commit_message`

A new helper walks the first-parent chain of the clone HEAD, skipping "Merge X into Y" commits, to find the user's actual last commit message:

```python
def _find_user_commit_message(self, cid, vault_commit, read_key) -> str:
    """Walk first-parent chain, skip merge commits, return the first
    non-merge commit's decrypted message."""
    ...
```

### Additional Safety Check: Tree Identity

Before triggering the pull step, `push()` now also checks whether the clone HEAD tree is already identical to the named HEAD tree. If they match, nothing needs to be pushed (the files are already in sync):

```python
if named_commit_id:
    _vc = Vault__Commit(...)
    if (str(_vc.load_commit(clone_commit_id, read_key).tree_id) ==
            str(_vc.load_commit(named_commit_id, read_key).tree_id)):
        return dict(status='up_to_date', message='Nothing to push (files unchanged)')
```

This guards against creating an empty "push" after a previous push already synced the files (even though commit IDs differ because the clean commit has a different ID).

### First-Push Fix

On a vault's **first push**, `_upload_bare_to_server` pre-uploads all local objects. The subsequent `build_push_operations` then filters out redundant uploads and only executes the `write-if-match` ref update. However, the clean `push_target_id` commit is created **after** `_upload_bare_to_server` runs, so it would never be uploaded.

Fix: the first-push filter now explicitly keeps the `push_target_id` commit upload:

```python
if first_push:
    push_target_fid = f'bare/data/{push_target_id}'
    operations = [op for op in operations
                  if op['op'] == 'write-if-match'
                  or op.get('file_id') == push_target_fid]
```

---

## Before vs After

| Scenario | Before | After |
|----------|--------|-------|
| `sgit push` (no remote changes) | Named branch = clone commit (may be merge commit) | Named branch = new clean commit with same tree |
| `sgit push` after internal pull creates merge commit | Named branch = merge commit (**BUG**) | Named branch = new clean commit, no merge parents |
| `sgit push` twice without new commits | Named branch ref updated needlessly | Returns `up_to_date` (tree identity check) |
| `sgit log --graph` after push | Merge commits leaked to right lane | Named branch lane shows only clean commits |
| Commit IDs on named branch | Same as clone branch commit ID | Different (new commit created per push) |

---

## Breaking Changes

### For Users

**None.** File contents are unchanged. Vaults that have already been contaminated will still show old merge commits in history (the fix prevents future contamination; it does not rewrite existing history). All `sgit` commands continue to work as before.

### For Developers / Tests

**One test updated**: `test_push_updates_named_branch_ref` in `test_Vault__Sync__Push.py`.

**Old assertion** (no longer valid):
```python
assert clone_ref == named_ref   # named branch was set to the clone commit
```

**New assertion** (what we actually guarantee):
```python
# Named branch is set (non-empty)
assert named_ref is not None and named_ref != ''
# Named branch commit has ≤ 1 parent (no merge commits)
assert len(list(named_commit.parents or [])) <= 1
# Named branch carries the same file tree as clone HEAD
assert str(named_commit.tree_id) == str(clone_commit.tree_id)
```

### Protocol / API Compatibility

**No breaking changes to the API or vault format.** The named branch now stores one extra commit object per push (the clean `push_target_id`), but these are standard commit objects indistinguishable from any other commit. All existing vault encryption, tree, and blob formats are unchanged.

---

## Test Coverage

All 977 existing unit tests pass. No new test files added (the change is tested by the existing push/pull/clone test suite and the updated `test_push_updates_named_branch_ref` assertion).
