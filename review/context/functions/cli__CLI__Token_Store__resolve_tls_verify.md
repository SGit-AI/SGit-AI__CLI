## `resolve_tls_verify` in sgit_ai/cli/CLI__Token_Store.py (L32-L48)

```python
# L35-L48
if verify_flag is False: return False
if verify_flag is True:  return True
if not directory:        return True
try:
    from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
    default = Vault__Remote_Manager().get_default(directory)
    if default is not None:
        return bool(default.tls_verify)
except Exception:
    pass
return True
```

**Purpose:** Decide whether TLS certificates are verified: CLI flag, else the default remote's recorded `tls_verify`, else `True`.

**Inputs & Assumptions:**
- `verify_flag`: `True`/`False`/`None` from argparse (`--verify-tls` / `--no-verify-tls`, per comment L33-L35).
- `directory`: vault dir. `Vault__Remote_Manager.get_default` (`sgit_ai/core/Vault__Remote_Manager.py:L58-L65`) reads `.sg_vault/local/remotes.json` (L111-L117) — a plain JSON file written by `sgit remote add` (umask mode, L119-L123). Its `tls_verify` field can turn verification OFF for every later command in that clone. Trust: same-user file (A6 can plant it; TM-F03's path guard protects `.sg_vault` from VAULT content writes, so a vault author cannot).
- Any exception while reading remotes (corrupt JSON, schema error) → `True` (L46-L48): fails toward verifying.

**Outputs & Effects:** bool; pure.

**Cross-Function Dependencies:** `Vault__Remote_Manager.get_default` (external-source-available: returns the `is_default` remote else the FIRST remote, L59-L65). Callers: `resolve_remote` L71, L106; `CLI__Vault.py:L212`, `CLI__Main.py:L1132` (with `directory=None` → flag or `True`).

**Open Questions:** none.
