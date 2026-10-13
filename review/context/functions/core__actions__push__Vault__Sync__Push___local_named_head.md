## `_local_named_head` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L597-L606)

**Purpose:** The named-branch head this clone knows locally (cloned-from or last pulled), used by `_push_branch_only` as the chain stop when the server has no clone ref yet (L638).

**Inputs & Assumptions:** `directory`, `read_key`. Local only: `_init_components`, index, config, `read_ref`. Any exception → `''` (L605-L606).

**Outputs & Effects:** commit id or `''`; no writes. With `''`, `fetch_commit_chain` gets `stop_at=None` (L641) and walks the whole history (limit 100), so a branch-only push re-sends up to 100 commits and their blobs.

**Cross-Function Dependencies:** callees `Vault__Sync__Base._init_components`, `_read_local_config`, `Vault__Branch_Manager.load_branch_index/tracked_named_branch`, `Vault__Ref_Manager.read_ref`. Caller: `_push_branch_only` L638.

**Open Questions:** none.
