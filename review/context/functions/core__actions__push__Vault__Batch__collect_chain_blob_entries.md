## `collect_chain_blob_entries` in sgit_ai/core/actions/push/Vault__Batch.py (L172-L216)

**Purpose:** Every blob referenced by **any** commit being pushed (not only the head tree), as `[{'blob_id': ...}]`, so an older version of a file changed again before the push is uploaded along with the tree that references it (docstring L176-L183: 41 dangling references found on a production vault).

**Inputs & Assumptions:**
- `commit_chain`, `named_commit_id` (boundary, skipped L210-L211), `obj_store`, `read_key`, `skip_missing_trees`.
- Local objects only; trusted.

**Outputs & Effects:** list of dicts in first-seen order; no side effects.

**Block-by-Block:**
```python
# L193-L207
def walk(tree_id):
    if not tree_id or tree_id in visited_trees: return
    visited_trees.add(tree_id)
    if skip_missing_trees and not obj_store.exists(tree_id): return
    tree = json.loads(self.crypto.decrypt(read_key, obj_store.load(tree_id)))
    for entry in tree.get('entries', []):
        bid = entry.get('blob_id')
        if bid and bid not in seen_blobs:
            if not obj_store.exists(bid): continue
            seen_blobs.add(bid); blob_ids.append(bid)
        walk(entry.get('tree_id'))
```
- **What:** DFS over trees, each decrypted once; blobs not present locally are skipped (comment L204: sparse / scoped / pulled history — "it came from the server, so it is there").
- **Assumes:** a blob absent locally is present on the server. That holds for blobs that arrived by pull (verified download); it is not checked here: `nothing found`. A tree whose blob is missing both locally and remotely is pushed with a dangling reference — the next clone's `verify-signatures`/download refuses or warns (TM-F02 row), push does not.
- **Assumes:** `obj_store.load(tree_id)` exists for an unscoped clone (raises `Vault__Object_Missing_Error` otherwise → caught by the per-commit `except Exception: continue` at L214-L215, which silently drops **that whole commit's blobs**).

```python
# L209-L215
for cid in commit_chain:
    if not cid or cid == named_commit_id: continue
    try: walk(str(vault_commit.load_commit(cid, read_key).tree_id))
    except Exception: continue
```
- **Assumes:** an exception means "absent commit object: nothing of it to push" (L215). Any other exception (a decrypt failure, a malformed tree) is swallowed the same way; the commit object itself is still pushed by `build_push_operations` L77-L82 (it loads the commit separately and would raise there). Observation.

**Cross-Function Dependencies:**
- Callees: `Vault__Commit.load_commit`, `Vault__Crypto.decrypt`, `Vault__Object_Store.exists/load`.
- Callers: `Vault__Sync__Push.push` L249-L251 (then filtered against `named_blob_ids`, L253-L257, L273-L279); `_push_branch_only` L668.

**Open Questions:** none.
