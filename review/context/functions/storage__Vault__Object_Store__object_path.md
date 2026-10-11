## `object_path` in sgit_ai/storage/Vault__Object_Store.py (L96-L97)

```python
# L97
return os.path.join(self.vault_path, BARE_DATA_DIR, object_id)
```

**Purpose:** The on-disk location of an object: `<vault_path>/bare/data/<object_id>`.

**Inputs & Assumptions:**
- `object_id` (str): unvalidated; see `load`/`store_raw` for sources.
- Implicit: `self.vault_path : Safe_Str__Vault_Path` (L42). This is a `Safe_Str` with `regex = [^a-zA-Z0-9/\\_.\- ]`, `allow_empty = True`, and the **default** `regex_mode = REPLACE`, `strict_validation = False`, `replacement_char = '_'` (`sgit_ai/safe_types/Safe_Str__Vault_Path.py:L4-L10`; `osbot_utils/type_safe/primitives/core/Safe_Str.py:L18-L20, L77`). So assigning `vault_path=sg_dir` **rewrites** any character outside that set to `_`. Observed in this checkout: `'/home/u/vault~1' → '/home/u/vault_1'`, `'/home/u/café' → '/home/u/caf_'`, `'/home/u/a:b' → '/home/u/a_b'` (run against `Safe_Str__Vault_Path` directly). `tests/unit/safe_types/test_Safe_Str__Vault_Path__Boundary.py` (`test_semicolon_sanitized`, `test_pipe_sanitized`, …) pins the sanitising behaviour as intended for shell-ish characters.
- Precondition the code counts on: the sanitised `vault_path` names the same directory as the raw `directory` string that `Vault__Storage.<accessor>(directory)` and `os.path.join(directory, ...)` use elsewhere in the same operation (`Vault__Sync__Base._init_components` L365 builds `sg_dir = os.path.join(directory, SG_VAULT_DIR)` then passes it to `Vault__Object_Store(vault_path=sg_dir)` L376, `Vault__Ref_Manager(vault_path=sg_dir)` L377, `Vault__Key_Manager(vault_path=sg_dir)` L378, while `Vault__Branch_Manager.save_branch_index/load_branch_index` L83/L89 use `self.storage.index_path(directory, …)` with the raw string, and `Vault__Components.sg_dir = sg_dir` L390 is the raw string). For a vault root containing `~`, `:`, `+`, `@`, `,`, `(`, `)`, `'`, `é`, or any non-ASCII letter, the two conventions name different directories. **nothing found** that checks the round trip (`str(Safe_Str__Vault_Path(p)) == p`) anywhere; `tests/unit/safe_types/test_Safe_Str__Vault_Path.py` tests only ASCII/space paths; the hermetic test fixtures use `tempfile` paths (ASCII).

**Outputs & Effects:** Pure string.

**Cross-Function Dependencies:**
- Callers: `store` L48, `store_raw` L62, `store_at` L76, `load` L85, `exists` L94, `total_size` L133.
- The same field/pattern: `Vault__Ref_Manager.vault_path` (`_ref_path` L78-L79, `list_refs` L52, `is_initialized` L48), `Vault__Key_Manager.vault_path` (`_key_path` L78-L79, `list_keys` L73), `Vault__Reflog.vault_path` (`path` L28-L29), `Vault__Branch_Manager.vault_path` (declared L18, **never read** — Branch_Manager uses `storage` + raw `directory`), `Vault__Storage.vault_path` (declared L22, never read).

**Open Questions:**
- What happens operationally on a vault root with a character outside `[a-zA-Z0-9/\\_.\- ]`: object/ref/key/reflog reads and writes go to a sibling `_`-substituted path while index/config/working-copy writes go to the real one. Not reproduced here (would require creating such a directory); flagged as the precondition the whole storage layer rests on and that nothing enforces.
