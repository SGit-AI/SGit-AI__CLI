# Path accessors in sgit_ai/storage/Vault__Storage.py

All are one-line `os.path.join` builders over a caller-supplied `directory` (str, the vault root the user chose) and fixed constants (L6-L18). None validates, none touches the filesystem (except `is_vault`), none uses the class field `vault_path` (L22) — that field is declared and never read anywhere in this file. Trust of `directory`: trusted (the user's own working directory, from argv / `find_vault_root`).

## `sg_vault_dir` (L24-L25) → `<directory>/.sg_vault`
## `bare_dir` (L27-L28) → `<directory>/.sg_vault/bare`
## `local_dir` (L30-L31) → `<directory>/.sg_vault/local`
## `bare_data_dir` (L33-L34), `bare_refs_dir` (L36-L37), `bare_keys_dir` (L39-L40), `bare_indexes_dir` (L42-L43), `bare_pending_dir` (L45-L46), `bare_branches_dir` (L48-L49), `bare_cache_dir` (L51-L52), `bare_cache_value_dir` (L54-L55), `bare_cache_pointer_dir` (L57-L58)
Fixed sub-folders of `bare_dir`.

## `cache_path` (L60-L62) → `<bare_cache_dir>/<kind>/<cache_id>`
`kind` and `cache_id` are joined unvalidated. Callers: `Vault__Cache_Manager.save/load/exists/delete/list_ids` (L209, L223, L233, L236, L244) with `kind` from `kind_dir_name(kind)` (an enum) and `cache_id` derived by HMAC from the read key (`Vault__Crypto.derive_cache_value_file_id` L162 / `derive_cache_pointer_file_id` L173) or listed from the local folder (L248); `Vault__Cache_Repair.py:L249`. Nothing here establishes that `cache_id` has no separator; the derivation does (hex). Host-served cache objects reach disk through `Vault__Verified_Write.save` (`STORE_FILE_ID` L18-L19 admits `bare/cache/(value|pointer)/<leaf>`), not through this function.

## `cache_file_id` (L64-L67) → `'bare/cache/<kind>/<cache_id>'` (wire id, relative to `.sg_vault/`).

## `is_vault` (L83-L84) → `os.path.isdir(bare_dir(directory))`. No callers in `sgit_ai/` (only `tests/unit/sync/test_Vault__Storage.py::test_is_vault`).

## `vault_key_path` (L98-L99), `local_config_path` (L101-L102), `remotes_path` (L104-L105), `tracking_path` (L107-L108), `push_state_path` (L110-L111), `clone_mode_path` (L113-L114)
Fixed names under `local_dir`. `vault_key_path` and `clone_mode_path` name the two files that hold key material (threat model §2); their writers go through `write_private` (callers listed in that record).

## `object_path` (L116-L117), `ref_path` (L119-L120), `key_path` (L122-L123), `index_path` (L125-L126)
`<bare_*_dir>/<id>` with the id joined unvalidated. Only `index_path` has callers in this slice: `Vault__Branch_Manager.save_branch_index` L83 and `load_branch_index` L89, where `index_id` is either `secrets.token_hex` (L79) or `c.branch_index_file_id` = `keys['branch_index_file_id']` (HMAC-derived from the read key, `Vault__Sync__Base.py:L382,L389`). `object_path`/`ref_path`/`key_path` here are **not** what `Vault__Object_Store`, `Vault__Ref_Manager`, `Vault__Key_Manager` use — each of those has its own `_path` built from its own `vault_path` field (see the `Vault__Object_Store.object_path` record for the consequence).

**Open Questions:**
- Two parallel path conventions exist (`Vault__Storage.<x>(directory)` with a raw `str`, and `<Manager>.vault_path : Safe_Str__Vault_Path`). Whether they always name the same directory is examined in `storage__Vault__Object_Store__object_path.md`.
