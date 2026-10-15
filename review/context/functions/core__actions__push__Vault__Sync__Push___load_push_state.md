## `_load_push_state` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L727-L751)

**Purpose:** Resume support: load `local/push_state.json` when it matches `(vault_id, clone_commit_id, remote_url)`, else start fresh. The `blobs_uploaded` list it carries tells Phase A which blobs to **skip without asking the server**.

**Inputs & Assumptions:**
- `path` (local file, written by `_save_push_state` with mode 0600), `vault_id`, `clone_commit_id`, `remote_url` (`str(self.api.base_url)`, `push` L266).
- Trust: local file under `.sg_vault/local/` — the same trust level as the vault key. A pre-remote-scoped file without `remote_url` is a mismatch (docstring L733-L736).

**Outputs & Effects:** a `Schema__Push_State` (Schema__Push_State.py:L7-L16; `blobs_uploaded : list[Safe_Str__Object_Id]`). Any parse error → fresh state (L748-L749).

**Block-by-Block:**
- L738-L747: read, `Schema__Push_State.from_json` (Type_Safe validates ids against the object-id regex), compare the three keys.
- **Establishes:** blobs listed are skipped (`push` L279). The server is not consulted: `nothing found` re-verifying. A checkpoint from a push whose batch "succeeded" by an empty-body 2xx (see `_checked`) would persist the belief.

**Cross-Function Dependencies:** callers `push` L267. Tests: `test_Vault__Sync__Push__Coverage.py::Test_Vault__Sync__Push__PushState` (bad JSON, mismatched vault, matching/mismatched remote_url, legacy without remote_url).

**Open Questions:** none.
