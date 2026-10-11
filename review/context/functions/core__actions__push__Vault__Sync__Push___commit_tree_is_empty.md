## `_commit_tree_is_empty` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L702-L715)

**Purpose:** True when the commit's root tree has no entries (a fresh `init` vault), so the "nothing to push" path skips the resync check for an empty vault (L105).

**Inputs & Assumptions:** `commit_id`, local `obj_store`, `read_key`. Local only. Any exception → False (L714-L715), which means "not empty" → the resync check **runs** (`_is_first_push` / `_server_has_named_ref`), i.e. a missing or undecryptable local commit object leads to a server listing and possibly a full re-upload.

**Outputs & Effects:** bool; no writes.

**Cross-Function Dependencies:** `Vault__Commit.load_commit/load_tree`. Caller: `push` L105. Test: `test_Vault__Sync__Push__Coverage.py::test_commit_tree_is_empty_exception_returns_false_lines_345_346`.

**Open Questions:** none.
