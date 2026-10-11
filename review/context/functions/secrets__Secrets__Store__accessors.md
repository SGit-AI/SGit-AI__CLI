# `Secrets__Store` read/delete methods in sgit_ai/secrets/Secrets__Store.py

Fields (L12-L13): `store_path : Safe_Str__Vault_Path = None` (sanitised path — see Key_Manager accessors record; `CLI__Credential_Store.setup` L23-L24 assigns `os.path.join(home, 'vaults.enc')`), `crypto : Vault__Crypto`. All three methods: derive master key, decrypt whole store, act. Each is a full decrypt of the file.

---

## `get` (L26-L32)
Returns `entry['value']` or `None` when the alias is absent. Wrong passphrase raises `InvalidTag` from `_load_all` L56 rather than returning `None`. Caller: `CLI__Credential_Store.get_vault_key` L34. The returned vault key is printed in full by `sgit vault show` (`CLI__Vault.py:L1683-L1685`; TM-R14 context).

## `list_keys` (L34-L37)
Sorted aliases. Caller: `CLI__Credential_Store.list_vaults` L40.

## `delete` (L39-L46)
`False` if absent, else removes and `_save_all`s. Same read-modify-write race as `store`. Caller: `CLI__Credential_Store.remove_vault` L45 (no auto-lock check, no activity touch there). Tests: `test_Secrets__Store.py::test_delete_*`, `test_Secrets__Store__Edge_Cases.py::test_delete__then_get_returns_none`.
