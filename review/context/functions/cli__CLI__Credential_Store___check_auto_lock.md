## `_check_auto_lock` in sgit_ai/cli/CLI__Credential_Store.py (L82-L90)

```python
# L83-L90
lock_path = self._lock_state_path()
if not os.path.isfile(lock_path):
    return
with open(lock_path, 'r') as f:
    state = json.load(f)
last = state.get('last_activity', 0)
if time.time() - last > self.lock_timeout:
    self._lock()
```

**Purpose:** The "auto-lock on inactivity" (L69 comment): if the last recorded activity is older than `lock_timeout` (default 1800 s, L12; `Safe_UInt__Lock_Timeout` max 86400, `sgit_ai/safe_types/Safe_UInt__Lock_Timeout.py:L3-L6`) the lock-state file is deleted.

**Inputs & Assumptions:**
- Implicit: `lock-state.json` under `_sg_send_dir` (plain JSON, umask mode, written by `_touch_activity`). Trust: same-user file; `json.load` errors or a non-numeric `last_activity` (TypeError at L89) propagate.
- Implicit: wall clock `time.time()`. A clock moved backwards never locks.

**Outputs & Effects:**
- Either nothing or `_lock()` → the file is removed (L92-L95).
- What "locked" means: nothing. The callers (`get_vault_key` L32-L36, `list_vaults` L38-L42) call `_check_auto_lock()` and then proceed with the store operation unconditionally; the passphrase is required on every call anyway and the master key is never held between commands (except in the PBKDF2 LRU for the process lifetime). The threat model calls the lock "advisory" (TM-R11). `add_vault` and `remove_vault` do not consult it at all (L28-L30, L44-L45). Tests: `test_CLI__Credential_Store.py::test_auto_lock__recent_activity_passes`, `::test_auto_lock__expired_activity_locks` (asserts only that the file is gone).

**Cross-Function Dependencies:** `_lock_state_path` (L71-L73), `_lock` (L92-L95). Callers: `get_vault_key` L33, `list_vaults` L39.

**Open Questions:**
- unclear; what the lock state was intended to gate. No code path reads it other than this check, and the check's only effect is deleting the file.
