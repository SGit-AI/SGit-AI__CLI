# Brief 16 — Brief 15 follow-ups (missing roundtrip test + three small polish items)

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands as a small reviewer-fix style pass after the brief-15 branch merges. Estimated effort: ~1 hour.
**Author:** Villager orchestrator (Opus)
**Context:** review of `claude/sonnet-onboarding-oMP6A` commit `b39256f` (the brief 15 implementation).

---

## 1. Why this exists

The brief 15 implementation is solid — three live move bugs are fixed and 8 integration tests landed. Review surfaced one missing test and three small polish items that don't merit blocking the merge but should be addressed in a follow-up pass.

---

## 2. Missing test — `test_Vault__Sync__Move__Backup_Roundtrip.py`

Brief 15 §3d specified a 9th integration test that wasn't in the implementation. Add the file:

```
tests/integration/test_Vault__Sync__Move__Backup_Roundtrip.py
```

With one test:

```
test_move_backup_can_be_restored_under_old_key
  - sgit init <key>; commit; push (real server)
  - sgit vault move (creates a backup zip during step 7)
  - Locate the backup zip in <vault>/.sg_vault/backups/
  - sgit vault restore <zip-path> <fresh-dir> --mode bare (under the OLD vault-key)
  - Assert: restored .sg_vault/bare/data/ is byte-identical to the
    pre-move snapshot (compare hashes of every obj-cas-imm-* file).
  - Assert: restored config has the OLD vault_id.
```

This is the test that validates the disaster-recovery path the project lead is using right now to recover from a real-world incident. **It's the proof that the safety net works.** ~30 minutes to write following the same fixture pattern as the other three integration test files.

### 2a. Why this matters

The current 8 integration tests verify each operation independently (move works; backup works; restore works). They don't verify the **chained recovery scenario**: when the move workflow's step 7 produces a backup zip, that zip must be independently restorable later. If the backup format ever drifts from what restore expects, the safety net silently breaks. This test pins the contract.

---

## 3. Three small polish items (non-blocking)

### 3a. `_walk_tree` is recursive — convert to iterative

`Step__Move__Validate_Local._walk_tree` recurses on sub-trees. Python's default recursion limit is 1000; deeply nested trees (e.g. monorepos with deep package directories) could trip it. Convert to a stack-based loop:

```python
def _walk_tree(self, root_tree_id: str, vc, obj_store, read_key: bytes,
               visited_trees: set, visited_blobs: set, missing: list) -> None:
    stack = [root_tree_id]
    while stack:
        tree_id = stack.pop()
        if tree_id in visited_trees:
            continue
        visited_trees.add(tree_id)
        if not obj_store.exists(tree_id):
            missing.append(tree_id)
            continue
        try:
            tree = vc.load_tree(tree_id, read_key)
        except Exception:
            continue
        for entry in (tree.entries or []):
            blob_id     = str(entry.blob_id) if entry.blob_id else ''
            sub_tree_id = str(entry.tree_id) if entry.tree_id else ''
            if blob_id and blob_id not in visited_blobs:
                visited_blobs.add(blob_id)
                if not obj_store.exists(blob_id):
                    missing.append(blob_id)
            if sub_tree_id:
                stack.append(sub_tree_id)
```

Trivial change. No behavioural difference for normal vaults; safer for pathological cases.

### 3b. Comment the `startswith('obj-cas-imm-')` filter

`_collect_head_commit_ids` filters refs via `if commit_id and commit_id.startswith('obj-cas-imm-')`. This is a defence against decoded-but-unexpected ref values, but the silent skip could mask real refs corruption. Add a one-line comment so the next reader knows it's intentional defence-in-depth:

```python
# Defence-in-depth: refs should always decode to obj-cas-imm-* commit ids.
# A non-conforming value indicates either a partially-written ref or
# a refs-format change. Silent skip is intentional — Validate_Local's
# job is to catch missing objects, not to flag ref-format anomalies.
if commit_id and commit_id.startswith('obj-cas-imm-'):
    head_ids.append(commit_id)
```

### 3c. Replace the `.sg_vault_new/ → .sg_vault/` string hack

`cmd_vault_move` (in `CLI__Vault.py`) does:

```python
final_bak = result['backup_zip_path'].replace('.sg_vault_new/', '.sg_vault/')
```

This works but is fragile — any future renaming of the temp dir name breaks it silently. Better: have `Step__Move__Delete_Source` (which performs the atomic rename) update the path in the returned state to reflect the post-rename location. Then `cmd_vault_move` reads the corrected path directly.

Concretely, in `Step__Move__Delete_Source.execute`, after the `os.rename(new_sg_dir, sg_vault_dir)` succeeds:

```python
backup_path = state_dict.get('backup_zip_path', '')
if backup_path:
    # The rename moved .sg_vault_new/ → .sg_vault/, so update the path accordingly
    state_dict['backup_zip_path'] = backup_path.replace(
        os.path.join(directory, '.sg_vault_new'),
        os.path.join(directory, '.sg_vault'),
    )
```

Then drop the `.replace(...)` from `cmd_vault_move`. The CLI just prints whatever `result['backup_zip_path']` says, which is now correct by construction.

---

## 4. Tests for §3 polish items

- §3a (iterative `_walk_tree`): no new test required — the existing graph-walk regression test (`test_move_validates_full_commit_graph_before_proceeding`) covers the behaviour. Could optionally add a "very deep tree" stress test (1000-level nesting) as a regression marker, but defer.
- §3b (filter comment): no test — comment is documentation.
- §3c (path-update in Delete_Source): add a unit test verifying that after the rename step, `state.backup_zip_path` points at `.sg_vault/backups/...` not `.sg_vault_new/backups/...`.

---

## 5. Order of work

1. **§2 first** — add the missing roundtrip integration test. This is the highest-value item; pins the disaster-recovery contract.
2. **§3c** — clean the path-update logic. One test, ~15 minutes.
3. **§3a** — iterative `_walk_tree`. ~10 minutes.
4. **§3b** — filter comment. ~2 minutes.

Total: ~1 hour including reviewer fix pass.

---

## 6. Verification checklist

When done:

- 9 integration tests in `tests/integration/test_Vault__Sync__Move__*` and friends (the existing 8 plus the new roundtrip).
- The roundtrip test passes against the real local server fixture.
- `cmd_vault_move` prints the correct post-rename backup path without using `str.replace()`.
- A unit test asserts the post-rename path correctness in `Step__Move__Delete_Source`.
- `_walk_tree` no longer recurses.
- All 3,442+ unit tests still pass.

---

## 7. Out of scope

- The brief 12 items (silent `except: pass` in `_reencrypt_objects` × 7 sites, `store_at` refactor, cleanup state edge case) — those stay in brief 12.
- Filling integration tests for clone-branch / pull / fetch / migrate / etc. — separate follow-up brief per the brief 15 §4 plan.
- Deeper validation of the move workflow (e.g. checking the new vault on the server actually has all objects post-push) — possible future enhancement but not flagged today.

---

## 8. Why this is small and worth doing now

The roundtrip test is the missing 9th of 9 — closing the gap is a small, focused piece of work that pins the safety-net contract. The three polish items are the kind of small smell that accumulates if not addressed promptly. Together: ~1 hour of dev + reviewer time to bring the brief-15 work to fully-done.

The dev who lands this is welcome to fold it into the next reviewer-fix pass alongside the brief-12 items if both are ready at the same time. Otherwise it's a clean standalone pass.
