## `load_clone_mode` in sgit_ai/cli/CLI__Token_Store.py (L193-L203)

```python
# L194-L203
import json
from sgit_ai.storage.Vault__Storage import Vault__Storage
path = Vault__Storage().clone_mode_path(directory)
if os.path.isfile(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        pass
return {'mode': 'full'}
```

**Purpose:** The CLI's reader of `.sg_vault/local/clone_mode.json` (which, for a read-only clone, HOLDS THE READ KEY).

**Inputs & Assumptions:** `directory`. The file was written by `write_private` (0600) from `Schema__Clone_Mode.json()` (`Step__Clone__ReadOnly__Setup_Config.py:L34-L42`, `Vault__Attach.py:L82`).

**Outputs & Effects:**
- Returns the RAW dict — no `Schema__Clone_Mode.from_json`, so `read_key`/`vault_id` are not validated here (contrast the schema path's `Safe_Str__Write_Key` 64-hex and `Safe_Str__Vault_Id`).
- A present-but-unparseable file → `{'mode': 'full'}` (L201-L203). Two readers disagree on this case: `Vault__Sync__Base._read_clone_mode` (L279-L298) raises `Vault__Clone_Mode_Corrupt_Error` ("fail-closed", its docstring) for the same file, and `Vault__Diff._read_clone_mode_safe` (L566-L579) returns `None` (falls back to the vault_key path). So for a corrupt read-only clone: `sgit info`/`resolve_read_key` say "full" and then find no `vault_key` file (→ `None`), while sync operations refuse. Both recorded; tests: `test_CLI__Token_Store__Clone_Mode.py::test_load_clone_mode_corrupted_file_returns_full`.

**Cross-Function Dependencies:** `Vault__Storage.clone_mode_path` (L113-L114). Callers: `resolve_read_key` L221, `CLI__Vault.py:L778,L957,L1713`, `CLI__Doctor.py:L211`. `cmd_info` L1718-L1725 prints `read_key` from this dict (as `sgit_private_read_…`).

**Open Questions:** none.
