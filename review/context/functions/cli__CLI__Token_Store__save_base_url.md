## `save_base_url` in sgit_ai/cli/CLI__Token_Store.py (L151-L165)

```python
# L152-L165
if not directory or not base_url: return
sg_vault_dir = os.path.join(directory, '.sg_vault')
if not os.path.isdir(sg_vault_dir): return
local_dir = self._local_dir(directory); os.makedirs(local_dir, exist_ok=True)
base_url_path = os.path.join(local_dir, BASE_URL_FILE)
with open(base_url_path, 'w') as f:
    f.write(base_url)
try:
    os.chmod(base_url_path, stat.S_IRUSR | stat.S_IWUSR)
except OSError:
    pass
```

**Purpose:** Records the server URL in `.sg_vault/local/base_url` (the legacy fallback `resolve_remote` reads at L101). This file is what pins a clone to its server when no `remotes.json` exists.

**Inputs & Assumptions:** `base_url` (str): argv or the API's effective URL (`CLI__Vault.py:L247,L296,L379`, `CLI__Create.py:L58`). Not a secret.

**Outputs & Effects:**
- Written with plain `open('w')` THEN `chmod 0600` (L160-L165): the write-then-chmod pattern that the threat model says was removed for SECRET files (TM-F16). Here it persists because the URL is not key material; a symlink at `base_url_path` IS followed by `open('w')` (contrast `Vault__Secret_File`). `chmod` failure is swallowed. Tests: `tests/unit/sync/test_Vault__Sync__File_Modes.py::test_token_store_save_base_url_is_0600`, `test_CLI__Token_Store.py::test_save_base_url_chmod_oserror_silenced_lines_79_80`.
- Not atomic.

**Cross-Function Dependencies:** `_local_dir`. Callers: `resolve_base_url` L26, `CLI__Vault.py:L123,L247,L296,L379,L1325,L1603`, `CLI__Main.py:L940`, `CLI__Create.py:L58`.

**Open Questions:** none.
