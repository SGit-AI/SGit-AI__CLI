## `load_vault_key` in sgit_ai/cli/CLI__Token_Store.py (L182-L191)

```python
# L183-L191
if not directory: return ''
vault_key_path = os.path.join(directory, '.sg_vault', 'local', 'vault_key')
if not os.path.isfile(vault_key_path):
    vault_key_path = os.path.join(directory, '.sg_vault', 'VAULT-KEY')
if os.path.isfile(vault_key_path):
    with open(vault_key_path, 'r') as f:
        return f.read().strip()
return ''
```

**Purpose:** Reads the full vault key (prefixed `sgit_private_vault_…` form) from a full clone, with the legacy `VAULT-KEY` fallback. The CLI's reader; the core has its own copy of the same logic (`Vault__Sync__Base._read_vault_key` L34-L42) and several action classes a third (`Vault__Diff.py:L594-L596`, `Vault__Revert.py:L158-L160`, `Vault__Branch_Switch.py:L474-L476`).

**Inputs & Assumptions:** `directory`. The file was written by `write_private` at 0600; the read `open('r')` follows a symlink at the path. Content trusted as a vault key by every caller (`resolve_read_key` L219 "a vault key by definition").

**Outputs & Effects:** string or `''`; pure read. Callers print it in full: `CLI__Vault.cmd_vault_show_key` L1692-L1699, `cmd_info` L1735-L1760 (TM-R14 "`sgit vault info` prints the full vault key").

**Cross-Function Dependencies:** none internal. Callers: `resolve_read_key` L217, `CLI__Vault.py:L1294,L1366,L1562,L1692,L1735`, `CLI__Doctor.py:L207`. Tests: `test_CLI__Token_Store.py::test_load_vault_key_*`.

**Open Questions:** none.
