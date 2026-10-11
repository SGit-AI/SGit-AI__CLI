# Small methods in sgit_ai/storage/Vault__Object_Store.py

## `exists` (L93-L94)
`os.path.isfile(self.object_path(object_id))`. Follows symlinks. Callers: `resolve_id` L108, `verify_integrity` L137, `Vault__Sync__Base.fetch_tree_lazy` L622/L643, `Vault__Sync__Sparse` L126, `Vault__Sync.fetch` L206, `Vault__Sync__Tag._load_tag` L187, `Vault__Sync__Scope` L75, `Vault__Sync__Status` L279, `Vault__Key_Fetch` uses `key_manager.key_exists` instead.

## `all_object_ids` (L121-L125)
Lists `bare/data`, keeping names that start with `obj-cas-imm-` (L125); missing dir → `[]`. Names not matching the prefix (e.g. `obj-<hex>` from GC drain, or planted files) are invisible to every consumer (fsck, gc, `object_count`, `total_size`, `resolve_id`).

## `object_count` (L127-L128), `total_size` (L130-L134)
Derived from `all_object_ids`; `total_size` uses `os.path.getsize` per id (follows links).

## `verify_integrity` (L136-L140)
`exists` → `load` → `crypto.object_id_matches(object_id, ciphertext)` at the id's own width (L140 comment: mixed vaults verify). False for a missing object. `tests/unit/objects/test_Vault__Object_Store.py::test_verify_integrity_*`.

## `_compute_id` (L142-L143)
`crypto.compute_object_id(ciphertext, int(self.id_hex_len or 12))`. `id_hex_len : Safe_UInt = Safe_UInt(12)` (L44); `compute_object_id` raises `ValueError` for widths other than 12/32 (`Vault__Crypto.py:L187-L188`), so a corrupt `format` value cannot produce a third width — `Vault__Format.id_hex_len` (L55-L56) maps through `ID_HEX_LEN` and `format_of` (L48-L53) falls back to format 1 for anything unknown.

## Exception constructors
`Vault__Object_Collision_Error.__init__` (L20-L23): message names the id. `Vault__Object_Missing_Error.__init__` (L37-L38): single-message constructor because the workflow runner re-raises as `type(exc)(str(exc))` (L33-L34 comment).
