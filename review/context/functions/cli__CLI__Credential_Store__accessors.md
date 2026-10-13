# `CLI__Credential_Store` thin wrappers in sgit_ai/cli/CLI__Credential_Store.py

Fields (L16-L17): `secrets : Secrets__Store`, `lock_timeout : Safe_UInt__Lock_Timeout = DEFAULT_LOCK_TIMEOUT` (1800). Constants L9-L12: home `~/.sg-send`, file `vaults.enc`, `lock-state.json`.

---

## `add_vault` (L28-L30)
`secrets.store(passphrase, alias, vault_key)` then `_touch_activity()`. No `_check_auto_lock`. Caller: `CLI__Vault.cmd_vault_add` L1661 — the vault key arrives via `--vault-key` argv or a `getpass` prompt (`CLI__Vault.py:L1660`).

## `get_vault_key` (L32-L36)
`_check_auto_lock()`; `secrets.get(...)`; `_touch_activity()`; return. The lock check never prevents the `get` (see `_check_auto_lock`). Caller: `CLI__Vault.cmd_vault_show` L1683 (prints the key), `resolve_vault_key` L52.

## `list_vaults` (L38-L42)
Same shape with `secrets.list_keys`. Caller: `CLI__Vault.cmd_vault_list` L1666.

## `remove_vault` (L44-L45)
`secrets.delete(...)` — no lock check, no touch. Caller: `CLI__Vault.cmd_vault_remove` L1675.

## `_lock_state_path` (L71-L73)
`os.path.join(getattr(self, '_sg_send_dir', SG_SEND_HOME), LOCK_STATE_FILE)`. Uses the raw `home` string, not the sanitised `store_path` (see `setup`).

## `_lock` (L92-L95)
Removes the lock-state file if present. The whole of "locking".
