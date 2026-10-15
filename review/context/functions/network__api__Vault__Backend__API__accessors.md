# `Vault__Backend__API` — sgit_ai/network/api/Vault__Backend__API.py (L7-L29)

Thin adapter: fields `api : Vault__API`, `vault_id : Safe_Str__Vault_Id`, `write_key : Safe_Str__Write_Key` (L9-L11; `Safe_Str__Write_Key` requires exactly 64 lower-hex, Safe_Str__Write_Key.py:L5-L16). Every method forwards to `Vault__API` with `str(self.vault_id)` / `str(self.write_key)`. **No callers in `sgit_ai/`** (see `Vault__Backend__accessors`).

## `read` (L13-L14) → `api.read(vault_id, file_id)`.
## `write` (L16-L17) → `api.write(vault_id, file_id, write_key, data)`.
## `delete` (L19-L20) → `api.delete(vault_id, file_id, write_key)`.
## `list_files` (L22-L26)
`api.list_files(vault_id, prefix)`; if the API returned a dict, `result.get('files', [])` (L24-L26 — `Vault__API.list_files` already does this, L356-L358, so the branch is reachable only with a double that returns a dict). Tests: `test_Vault__Backend__API.py::test_list_files_with_dict_returning_api*`.
## `batch` (L28-L29) → `api.batch(vault_id, write_key, operations)` — unlike the base class, CAS reaches the API.

Trust and checks: identical to the underlying `Vault__API` methods; this class adds none. No open questions.
