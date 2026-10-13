## `_server_has_named_ref` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L765-L772)

**Purpose:** On the "heads equal, tree not empty" path: does the server's `bare/refs/` listing contain the named ref id? If not, push resyncs the whole `bare/` tree. An error is an error, never "absent" (docstring L766-L767).

**Inputs & Assumptions:** `vault_id`, `named_ref_id`. Server read: `list_files(vault_id, 'bare/refs/')`.

**Outputs & Effects:** `any(named_ref_id in f for f in remote_refs)` — a **substring** test over each listed name (L772), tolerant of `bare/refs/` prefixes. Raises on a listing error (L770-L771; test `test_server_has_named_ref_exception_is_an_error`).

**Assumes:** the listing is truthful; a listing that omits the ref makes the client plain-write every local `bare/` file (`_upload_bare_to_server`) over the server's — the same consequence as `_is_first_push`. The code already read the server's ref at `push` L86 (`_require_readable_server_ref`) and does not reconcile the two answers: `nothing found`.

**Cross-Function Dependencies:** callee `Vault__API.list_files`. Caller: `push` L107.

**Open Questions:** none.
