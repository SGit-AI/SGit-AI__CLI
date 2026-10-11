## `resolve_token` in sgit_ai/cli/CLI__Token_Store.py (L14-L21)

```python
# L15-L21
if token:
    if directory:
        self.save_token(token, directory)
    return token
if not directory:
    return ''
return self.load_token(directory)
```

**Purpose:** Resolve the access token for a network command: an explicit `--token` wins and is PERSISTED to the vault's `.sg_vault/local/token` as a side effect; otherwise the saved token is loaded. Used by nearly every network command (`CLI__Vault.py` ~20 sites, `CLI__Branch.py`, `CLI__Tag.py`, `CLI__Diff.py`, `CLI__Doctor.py`, `CLI__Main._clone_family_sync` L1130).

**Inputs & Assumptions:**
- `token` (str or None): argv. Trust: **untrusted** content; it is a bearer secret (threat model §2 "Write key / access token").
- `directory` (str or None): the vault directory; `None` at `CLI__Main.py:L1130`, `CLI__Vault.py:L210`, `CLI__Create.py:L37` (no persistence).
- Precondition for the save: `.sg_vault` exists (`save_token` L128-L129 returns silently otherwise).

**Outputs & Effects:**
- Returns the token string or `''`.
- Side effect: `save_token` writes the token at 0600 via `write_private`. A token passed once on the command line is thereafter used by every later command in that clone without being asked for again. Tests: `tests/unit/cli/test_CLI__Token_Store.py::test_resolve_token_with_token_and_directory_saves_and_returns`, `::test_resolve_token_no_token_loads_from_directory`.

**Cross-Function Dependencies:** `save_token` (L124-L134), `load_token` (L136-L149). Callers assume `''` means "no token" and `Vault__API` then sends no auth headers (`Vault__API.py:L84-L87`).

**Open Questions:** none.
