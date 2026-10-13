## `setup` in sgit_ai/cli/CLI__Credential_Store.py (L19-L26)

```python
# L20-L26
home = sg_send_dir or SG_SEND_HOME
os.makedirs(home, exist_ok=True)
if not self.secrets.store_path:
    self.secrets = Secrets__Store(store_path=os.path.join(home, VAULTS_ENC_FILE), crypto=Vault__Crypto())
self._sg_send_dir = home
return self
```

**Purpose:** Binds the store to `~/.sg-send/vaults.enc` (`SG_SEND_HOME = expanduser('~/.sg-send')`, L9) and remembers the home for the lock-state file. Called once per command by `CLI__Vault.setup_credential_store` (`CLI__Vault.py:L1655-L1656`, from `CLI__Main.py:L833`).

**Inputs & Assumptions:**
- `sg_send_dir` (str or None): override, used by tests (`tests/unit/cli/test_CLI__Credential_Store.py:L14`) and whatever `CLI__Main` passes (L833 passes nothing in the grep'd line).
- Implicit: `self.secrets` — Type_Safe auto-instantiates a `Secrets__Store` with empty `store_path` (annotation without default, L16), so the `if not self.secrets.store_path` branch runs on a fresh instance.
- `os.makedirs(home)` uses the umask (typically 0755) for `~/.sg-send`.
- `store_path` becomes a `Safe_Str__Vault_Path`: sanitised (chars outside `[a-zA-Z0-9/\\_.\- ]` → `_`). A home directory such as `/home/josé/.sg-send` or one containing `+` would be rewritten, and the store would live at (and be looked for at) the rewritten path, while `_lock_state_path` (L71-L73) uses the UNSANITISED `home` string. **nothing found** checking the two agree.
- `self._sg_send_dir = home`: an attribute with no annotation on a Type_Safe class. `Type_Safe.__setattr__` → `type_safe_step_set_attr.setattr` (`Type_Safe__Step__Set_Attr.py:L138-L155`) resolves and validates against annotations; for an unannotated `str` it passes through (`resolve_value__int_str` L50-L56). Established in practice by every test in `test_CLI__Credential_Store.py` calling `setup()` (L14) and by `::test_sg_send_dir_created`.

**Outputs & Effects:** directory created; `self.secrets` replaced; `self._sg_send_dir` set; returns self.

**Cross-Function Dependencies:** `Secrets__Store` constructor; `Vault__Crypto()`. Callers: `CLI__Vault.setup_credential_store` L1656.

**Open Questions:**
- unclear; need to inspect `CLI__Main.py:L825-L840` to see whether `setup_credential_store` is called for EVERY command (creating `~/.sg-send` as a side effect) or only for credential commands.
