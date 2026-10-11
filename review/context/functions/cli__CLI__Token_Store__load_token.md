## `load_token` in sgit_ai/cli/CLI__Token_Store.py (L136-L149)

```python
# L137-L149
if not directory: return ''
token_path = os.path.join(self._local_dir(directory), TOKEN_FILE)
if os.path.isfile(token_path):
    with open(token_path, 'r') as f: return f.read().strip()
legacy_path = os.path.join(directory, '.sg_vault', TOKEN_FILE)
if os.path.isfile(legacy_path):
    with open(legacy_path, 'r') as f: return f.read().strip()
return ''
```

**Purpose:** Reads the saved token: `.sg_vault/local/token`, else the legacy `.sg_vault/token`.

**Inputs & Assumptions:** `directory`. The read `open('r')` follows a symlink at either path (A6 could redirect it to another file; what they gain is the CLI sending THAT file's first line as a bearer token to the server). **nothing found** refusing links on this read; threat model TM-F27's `O_NOFOLLOW` reads cover the secret scan, not this. Legacy location is read but never written (no migration).

**Outputs & Effects:** token or `''`; pure read. Tests: `test_CLI__Token_Store.py::test_load_token_legacy_fallback`, `::test_load_token_primary_takes_precedence_over_legacy`.

**Cross-Function Dependencies:** `_local_dir`. Callers: `resolve_token` L21, `CLI__Vault.py:L115,L1378,L1422,L1447,L1756`.

**Open Questions:** none.
