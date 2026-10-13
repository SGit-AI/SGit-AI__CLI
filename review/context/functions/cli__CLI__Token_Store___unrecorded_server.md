## `_unrecorded_server` in sgit_ai/cli/CLI__Token_Store.py (L108-L119)

```python
# L113-L119
import sys
from sgit_ai.network.api.Vault__API import Vault__API, DEFAULT_BASE_URL
server = Vault__API().default_base_url()
if server != DEFAULT_BASE_URL:
    print(f'warning: this vault records no server; using SGIT_DEFAULT_BASE_URL={server}. '
          f'Record one with `sgit remote add origin <url>` (or pass --base-url).', file=sys.stderr)
return server
```

**Purpose:** For a vault that recorded no server (pre-0.21 init), return the process default and SAY SO when an environment variable is what chose it (docstring L109-L112, review S1 / TM-F15).

**Inputs & Assumptions:**
- Implicit: `SGIT_DEFAULT_BASE_URL` via `Vault__API.default_base_url` (`sgit_ai/network/api/Vault__API.py:L73-L76`: env var else `https://dev.send.sgraph.ai`, L18). Trust: the process environment (A6 / CI config).

**Outputs & Effects:**
- Returns the server — INCLUDING the env-var value after warning. This function warns; it does not refuse. The refusal the threat model describes for unrecorded vaults (TM-F22: "`CLI__Main.run` pins the server per command"; `test_Security__Fixed__Server_Pin.py::test_an_unrecorded_vault_refuses_the_variable`, `::test_an_unrecorded_vault_records_the_default_on_first_use`) lives in `CLI__Main`, outside this slice. Within this slice, a caller reaching L103 of `resolve_remote` with the variable set proceeds against it (`tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_a_vault_with_no_recorded_server_names_the_redirect` checks the warning text).
- Nothing is written ("Never recorded, so unsetting it undoes it", L112).

**Cross-Function Dependencies:** `Vault__API.default_base_url` (external-source-available). Caller: `resolve_remote` L103 only.

**Open Questions:**
- unclear; whether every command that calls `resolve_remote` goes through `CLI__Main.run`'s pin first, so that this warning path is unreachable with the variable set. Needs the `CLI__Main` slice.
