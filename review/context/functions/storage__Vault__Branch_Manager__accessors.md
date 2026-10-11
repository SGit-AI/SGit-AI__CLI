# Lookup helpers in sgit_ai/storage/Vault__Branch_Manager.py

## `get_branch_by_id` (L99-L103)
First `branch` in `index.branches` with `str(branch.branch_id) == branch_id`, else `None`. Duplicate ids → first wins.

## `get_branch_by_name` (L105-L109)
Same by `name`. `display_name` is never used for lookup (schema comment `Schema__Branch_Meta.py:L62`). Callers include `Vault__Sync._fetch_branch_for_switch` L186 (name, then id), `Step__Clone__Download_Index` L109 (`'current'`), `Vault__Sync__Sparse` L219.

## Fields (L18-L22)
`vault_path : Safe_Str__Vault_Path = None` — declared, **never read** in this file. `crypto`, `key_manager`, `ref_manager`, `storage` — no defaults, so Type_Safe constructs empties when a caller omits them (tests); production passes all four (`Vault__Sync__Base.py:L379-L381`).
