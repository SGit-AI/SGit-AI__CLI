## `_collect_tree_objects` in sgit_ai/core/actions/push/Vault__Batch.py (L218-L244)

**Purpose:** Append a `write` op for a tree and, recursively, every sub-tree, de-duplicated through `uploaded_ids`. `skip_missing`: a scoped clone never fetched its siblings' trees; they are unchanged and already on the server.

**Inputs & Assumptions:** `tree_id`, `obj_store`, `read_key`, `operations` (mutated), `uploaded_ids` (mutated), `skip_missing`.

**Outputs & Effects:** appends ops; adds ids to `uploaded_ids` (including skipped-missing ones, L227, so they are not retried).

**Block-by-Block:**
- L224-L228: already handled / scoped-missing → return.
- L230-L234: load, append `write bare/data/<tree_id>`, mark.
- L237-L244: decrypt the tree JSON, recurse into `entries[*].tree_id`.
- **Assumes:** an unscoped clone holds every tree of every pushed commit (`obj_store.load` raises otherwise and `build_push_operations` propagates — `push` does not catch around `build_push_operations` L323, so the push fails before any batch is sent).
- **Assumes (skip_missing):** a tree absent locally is on the server: `nothing found` verifying.

**Cross-Function Dependencies:** caller `build_push_operations` L87-L88. Tests: `test_Vault__Batch__Coverage.py::Test_Vault__Batch__CollectTree` (visited skip, recursion).

**Open Questions:** none.
