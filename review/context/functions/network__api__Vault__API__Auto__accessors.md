# `Vault__API__Auto` one-line wrappers — sgit_ai/network/api/Vault__API__Auto.py

Each forwards to `_call(name, ...)` (L81-L100): `read` (L81-L82), `batch_read` (L84-L85), `presigned_read_url` (L87-L88), `list_files` (L90-L91), `write` (L93-L94), `delete` (L96-L97), `batch` (L99-L100). They carry the full `Vault__API` signatures, so every caller in core is unchanged (`Vault__Sync__Base.api : Vault__API`). Not wrapped: `delete_vault`, `tombstone_vault`, `presigned_initiate/complete/cancel`, `fetch_presigned`, `check_presigned_url` (inherited; see `_call`).

## `describe` (L102-L110)
Human-readable transport line: `local (folder, read-only)`, `static-http (GET fan-out, read-only)`, `api (live SG/API)`, or `auto (not yet resolved)`. Read by `CLI__Vault.describe_transport` (sgit_ai/cli/CLI__Vault.py:L62-L67). No state change; no open questions.
