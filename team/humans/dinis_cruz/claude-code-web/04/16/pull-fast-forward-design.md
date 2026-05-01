# Pull Fast-Forward: Design Document

**Date**: 2026-04-16
**Status**: Proposed
**Files affected**: `sgit_ai/sync/Vault__Sync.py`

---

## 1. Current Situation

### What pull() does today

Every `sgit pull` unconditionally creates a **"Merge current into local"** commit on the clone
branch, even when no local work has diverged from the named branch:

```python
# pull() — current code (simplified)
lca_id = fetcher.find_lca(clone_commit_id, named_commit_id)

if lca_id == named_commit_id:
    return 'up_to_date'            # clone is ahead of named — handled

# ALL other cases → three-way merge → new commit
merge_commit_id = vault_commit.create_commit(
    parent_ids = [clone_commit_id, named_commit_id],
    message    = 'Merge current into local',
    ...)
ref_manager.write_ref(clone_head_ref, merge_commit_id)
```

The missing branch: **`lca_id == clone_commit_id`** (named is strictly ahead of clone, nothing
locally diverged). In git this is a fast-forward. In sgit today it falls through to the three-way
merge and creates an unnecessary merge commit.

---

## 2. What the Design Was Trying to Do

The no-fast-forward decision was intentional. Creating a commit on every pull provides:

- **Provenance**: every merge is recorded — who merged which branch state into their clone, and when
- **Audit trail**: the DAG shows which user incorporated which remote state at what point in time
- **Traceability**: browsing a clone's log shows exactly when remote changes were integrated

This is a reasonable goal. The implementation chose to solve it at the **DAG/commit layer**.

---

## 3. Problems This Created

### Named-branch contamination

`push()` sets the named branch ref to the clone HEAD. When the clone HEAD is a
"Merge current into local" commit (which it almost always is after a pull), the named branch
gets a merge commit that carries clone-specific language and semantics:

```
sgit log --graph (named branch, right lane):
| * 4c10a900b081  Merge current into local   ← should never be here
```

### Merge-commit spam

Because EVERY pull creates a merge commit — even a simple "you're just 2 commits behind,
nothing changed locally" — the clone's log fills up with merge commits:

```
sgit log --oneline:
68b8a98eb879  Merge current into local   ← pull #5
20bc19e1a72b  Merge current into local   ← pull #4
13ffabedea2d  Merge current into local   ← pull #3
07bf99e197f3  Merge current into local   ← pull #2
5d9c5998a402  Merge current into local   ← pull #1
6a9d943b46ca  Add all trilogy PDFs...    ← actual user work
```

### "Folders with version control" promise broken

SGit vaults are marketed as "folders with version control." If Alice and Bob each clone the
same vault, their `sgit log` should look the same (plus their own local additions). With
merge-commit spam, two clones of the same vault show completely different histories even
when neither has done any work. This breaks the user-facing model.

### Wrong altitude for provenance

Provenance via DAG structure is fragile: merge commits carry clone-branch names
("Merge **current** into **local**"), which are meaningless on the shared named branch.
The right altitude for provenance is cryptographic: when vault content is double-encrypted
with a target user's public key, decryption of that content is provable evidence of access.
DAG commits cannot provide this guarantee anyway (commits can be created without actually
reading the files).

---

## 4. Proposed Solution: Fast-Forward Pull

### Core change

Mirror git's merge behaviour exactly:

| LCA result | git behaviour | sgit today | sgit after fix |
|------------|--------------|------------|----------------|
| `lca == named_commit` | up to date | up_to_date ✓ | up_to_date ✓ |
| `lca == clone_commit` | fast-forward | three-way merge + commit ✗ | fast-forward ✓ |
| `lca` is an ancestor of both | three-way merge | three-way merge ✓ | three-way merge ✓ |

**Fast-forward** means: checkout the named branch tree directly into the working directory,
advance the clone HEAD ref to `named_commit_id`. No new commit is created.

### Code change (pull())

```python
if lca_id == clone_commit_id:
    # Fast-forward: named branch is strictly ahead, no local divergence.
    named_commit = vault_commit.load_commit(named_commit_id, read_key)
    theirs_map   = sub_tree.flatten(str(named_commit.tree_id), read_key)
    ours_map     = sub_tree.flatten(str(ours_commit.tree_id), read_key) if clone_commit_id else {}

    self._checkout_flat_map(directory, theirs_map, obj_store, read_key)
    self._remove_deleted_flat(directory, ours_map, theirs_map)
    ref_manager.write_ref(str(clone_meta.head_ref_id), named_commit_id, read_key)

    return dict(status='merged', commit_id=named_commit_id,
                added=..., modified=..., deleted=..., conflicts=[])
```

### What changes in practice

**Normal workflow (solo user, linear history)**:

```
Before fix:                         After fix:
init → C_user → Merge → C_user2    init → C_user → C_user2
                  ↑                                    ↑
           unnecessary                           clean, no merge
```

**Concurrent workflow (two users edit different files)**:

Both cases still work. Bob's push triggers a pull inside push(). If Alice pushed in the
meantime:
- `lca = init` (genuine divergence) → three-way merge → merge commit on clone → push to named
- The named branch gets the merge commit (correct, intentional, git does the same)
- The merge commit's message is "Merge current into local" — could be improved cosmetically
  but is semantically correct

**Concurrent workflow (two users edit same file)**:

Three-way merge detects the conflict. Behaviour unchanged.

---

## 5. Why Three-Way Merges Are Already Automatic

The `three_way_merge()` function merges non-conflicting files automatically. A conflict only
arises when **both sides modified the same file** since their common ancestor. This is the
same rule as git. The `push()` fetch-first pattern already handles this:

```
push():
  1. pull() — merge any remote changes into clone (auto if no file overlap)
  2. push named branch to clone HEAD
```

After the fix, step 1 fast-forwards most of the time (no merge commit), and only does a
real merge when needed.

---

## 6. Breaking Changes

### For existing vaults

**None.** Existing vault data, encryption, tree, blob, and ref formats are unchanged.
Vaults that already have "Merge current into local" commits in their named branch history
will continue to work — the fix prevents future contamination but does not rewrite history.

### For `sgit log --graph` appearance

The clone log becomes cleaner over time. Fewer "Merge current into local" commits appear.
This is a UX improvement, not a breaking change.

### For multi-clone collaboration

**LCA computation becomes more reliable.** Because fast-forward sets clone HEAD = named
commit directly (the same object), subsequent LCA lookups between clone commits and named
commits find a clean ancestor chain. This actually fixes several edge-case bugs in
multi-clone delete/modify propagation scenarios.

### For the test suite

One test assertion may need updating:
- `test_push_updates_named_branch_ref` — currently asserts `clone_ref == named_ref`.
  After the fix, for a fresh vault (no concurrent pushes), `named_ref` IS still set to
  the user's commit (clone HEAD after the user's commit, which is a plain commit not a
  merge commit). So this test likely continues to pass unchanged.

### API / protocol compatibility

No changes to the wire protocol, vault format, or any public API.

---

## 7. What This Does Not Fix

- Existing "Merge current into local" commits already in named branch histories remain.
  These are harmless (LCA still works through them) but visible in `sgit log`.
- When genuine concurrent edits DO create a merge commit, that merge commit can still end
  up on the named branch via push(). This is correct git behaviour and acceptable.
- The cosmetic issue of "Merge current into local" as a commit message on the named branch
  (for genuine merges) could be improved in a follow-up by renaming to
  "Merge remote changes" or similar when writing to the named branch.
