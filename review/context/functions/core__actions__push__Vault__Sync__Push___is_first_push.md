## `_is_first_push` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L717-L725)

**Purpose:** "Does the server have any `bare/` file for this vault?" — the decision that makes push upload the whole local `bare/` tree with plain writes and write the ref against bytes it just uploaded. A failed listing is an error, never "empty" (docstring L718-L720, review S10).

**Inputs & Assumptions:** `vault_id`. Server read: `api.list_files(vault_id, 'bare/')`.

**Outputs & Effects:** `len(remote_files) == 0` (L725); raises `RuntimeError('could not list the vault on the server (...); nothing was pushed. Try again.')` on any exception (L723-L724).

**Block-by-Block:**
- L721-L724: the listing; error → raise (test `test_Vault__Sync__Push__Coverage.py::test_is_first_push_api_exception_is_an_error`).
- L725: empty → first push.
- **Assumes:** a successful empty listing is truthful. What the host can return that is accepted: `[]` (or `{'files': []}`, or a dict without `files`, or an empty body → `{}` → `[]` via `Vault__API.list_files` L356-L358) for a populated vault, which makes the client (a) re-upload every local `bare/` file as a plain write — including the local named ref file with its last-known head, every index and every key file — over whatever the server holds (`_upload_bare_to_server`), and (b) write the named ref by CAS against its own just-uploaded bytes (`push` L201, L349-L350, L356). Nothing cross-checks with `_server_named_commit_id` or `_require_readable_server_ref` (which did succeed at L86 if the server has the ref): `nothing found`. On the static transport, `list_files` returns `[]` when there is no manifest (Vault__API__Static.py:L212-L214) — then `_upload_bare_to_server` raises `Vault__Read_Only_Transport_Error` from `batch`, so nothing is written.

**Cross-Function Dependencies:** callee `Vault__API.list_files` (L347-L358; `Vault__API__Auto`/`Static` variants). Callers: `push` L106, L137.

**Open Questions:**
- unclear; the live server's `list` semantics when the vault exists but has no files vs. when the vault id is unknown (404 → error → push refuses; empty 200 → first push). `tests/unit/cli/doctor/test_Check__Vault_Known.py::test_warn_on_404_with_first_push_hint` suggests a 404 is the "not yet pushed" signal elsewhere.
