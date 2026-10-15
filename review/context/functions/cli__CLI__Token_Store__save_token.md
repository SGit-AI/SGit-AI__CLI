## `save_token` in sgit_ai/cli/CLI__Token_Store.py (L124-L134)

```python
# L125-L134
if not directory: return
sg_vault_dir = os.path.join(directory, '.sg_vault')
if not os.path.isdir(sg_vault_dir): return
local_dir  = self._local_dir(directory)
os.makedirs(local_dir, exist_ok=True)
token_path = os.path.join(local_dir, TOKEN_FILE)
from sgit_ai.storage.Vault__Storage import Vault__Storage
Vault__Storage().write_private(token_path, token)
```

**Purpose:** Persists the bearer access token to `.sg_vault/local/token`, owner-only.

**Inputs & Assumptions:**
- `token` (str): argv-supplied. Stored as PLAINTEXT (the token is not encrypted under any key; the file mode is its only protection — threat model §2 lists it with the write key as "derived in memory; token store").
- `directory`: must already be a vault (`.sg_vault` exists, L127-L129) — so `sgit clone --token` relies on the clone writing `.sg_vault` first (`CLI__Vault.py:L246,L294,L377` save after the clone result).
- `isdir` follows symlinks; `write_private` refuses a link AT the token path but not a linked `local/` directory (see `Vault__Secret_File.write`).

**Outputs & Effects:** 0600 atomic file (`tests/unit/sync/test_Vault__Sync__File_Modes.py::test_token_store_save_token_is_0600`). Silent no-op when not in a vault (`test_CLI__Token_Store.py::test_save_token_no_sg_vault_dir_returns_early`). The test `::test_save_token_chmod_oserror_silenced_lines_48_49` patches `os.chmod`, which this function no longer calls — the test documents the pre-F16 implementation and still passes.

**Cross-Function Dependencies:** `_local_dir` (L121-L122), `Vault__Storage.write_private` → `Vault__Secret_File.write`. Callers: `resolve_token` L17, `CLI__Vault.py:L246,L294,L377,L1324,L1605`, `CLI__Create.py:L56`.

**Open Questions:** none.
