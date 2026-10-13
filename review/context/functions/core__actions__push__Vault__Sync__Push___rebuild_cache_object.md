## `_rebuild_cache_object` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L563-L580)

**Purpose:** Delegates to `Vault__Cache_Manager.rebuild_for_path` so push and `cache repair` build identical objects (docstring L568-L569). Passes `existing.mutability` and the `blob_fetcher`.

**Inputs & Assumptions:** `path` (from a local or **server-fetched** cache object), `commit_id`, `tree_id`, `clone_flat`, `blob_fetcher` (server reads, unverified in this slice — see `_reconcile_cache`).

**Outputs & Effects:** the rebuilt object or `None` (path gone). No side effects of its own.

**Cross-Function Dependencies:** callee `Vault__Cache_Manager.rebuild_for_path` (external-source-available, not read). Caller: `_reconcile_cache` L494.

**Open Questions:** as in `_reconcile_cache` (verification of fetched blob bytes inside `rebuild_for_path`).
