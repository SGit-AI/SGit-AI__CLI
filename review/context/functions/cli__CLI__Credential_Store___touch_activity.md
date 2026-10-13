## `_touch_activity` in sgit_ai/cli/CLI__Credential_Store.py (L75-L80)

```python
# L76-L80
state = {'last_activity': time.time()}
lock_path = self._lock_state_path()
os.makedirs(os.path.dirname(lock_path), exist_ok=True)
with open(lock_path, 'w') as f:
    json.dump(state, f)
```

**Purpose:** Records "now" as the last credential-store activity.

**Inputs & Assumptions:** `_lock_state_path()` → `<home>/lock-state.json` with `home = getattr(self, '_sg_send_dir', SG_SEND_HOME)` (L72): if `setup()` was never called, the global default is used.

**Outputs & Effects:** plain `open('w')` (umask mode, not via `Vault__Secret_File`); content is a timestamp only, no secret. Not atomic. Called AFTER the store operation in `add_vault`, `get_vault_key`, `list_vaults` (L30, L35, L41), so a failed decrypt (wrong passphrase) does not touch.

**Cross-Function Dependencies:** `_lock_state_path`. Test: `test_CLI__Credential_Store.py::test_touch_activity_writes_timestamp`.

**Open Questions:** none.
