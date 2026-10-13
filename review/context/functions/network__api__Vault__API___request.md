## `_request` in sgit_ai/network/api/Vault__API.py (L394-L399)

**Purpose:** `_request_bytes` plus `json.loads`; an empty body becomes `{}`.

**Inputs & Assumptions:** as `_request_bytes`. The body is host-supplied JSON. `json.loads` on a non-JSON 2xx body raises `json.JSONDecodeError` (a `ValueError`, not a `RuntimeError`) — it is not caught here or by `_request_bytes`.

**Outputs & Effects:** returns the parsed object — **any** JSON type (list, string, number), not only dicts; callers index it as a dict (`result.get(...)` in `_batch_read_chunk` L195, `Vault__Batch._checked` L306; `list_files` L356 checks `isinstance(result, dict)` first). An empty 2xx body is `{}`, which `Vault__Batch._checked` (L305-L319) and `Vault__Index_Sync.require_written` (L250-L255) accept as a successful write: `nothing found` requiring an explicit `ok`.

**Cross-Function Dependencies:** callers: `write` L96, `delete` L105, `batch` L123, `_batch_read_chunk` L193, `presigned_*` L313, L326, L337, L345, `list_files` L355, `delete_vault` L365.

**Open Questions:** none.
