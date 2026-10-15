## `is_writable` in sgit_ai/storage/Vault__Path_Guard.py (L75-L79)

```python
# L79
return not self.is_protected(rel_path) and self.is_safe(base_dir, rel_path)
```

**Purpose:** The skip-predicate every write/delete loop over vault-supplied paths uses before touching a file (docstring L76-L78). True only when the path is neither structural nor escaping.

**Inputs & Assumptions:** `base_dir` trusted; `rel_path` untrusted (vault data). No preconditions.

**Outputs & Effects:** Pure bool; never raises (`is_safe` swallows the guard's exception, L83-L87). Note `is_safe` already calls `safe_join`, which already calls `is_protected` (L128), so the `is_protected` at L79 is redundant with what `is_safe` checks; harmless.

**Cross-Function Dependencies:**
- Callees: `is_protected` L89, `is_safe` L81 → `safe_join` L115.
- Callers (with the write/delete they gate): `Vault__Sync__Base._remove_deleted_flat` L531 (then `os.remove(os.path.join(directory, path))` at L533-L535 — **the deletion uses a plain `os.path.join`, not the `full` returned by `safe_join`**; since `is_writable` just passed, the two spell the same location, except that `safe_join` would have been built from `abspath(base)` — same file); `Vault__Sync__Sparse` L124; `Vault__Revert` L71; `Vault__Branch_Switch` L413; `Vault__Stash.pop` L94 (restore) and L107 (delete); `Vault__Restore` L178; `Vault__Merge__Resolve._resolve_ours` L82; `Vault__Merge__Abort` L46.
- Tests: `tests/unit/appsec/test_AppSec__Path_Traversal__Write_Sites.py::Test_AppSec__Remove_Deleted_Flat`; `tests/security/test_Security__Fixed__Hostile_Paths.py::Test_Fixed__Hostile_Paths__Vault_Data` (revert, switch, pull), `::test_stash_pop_contains_planted_names`.

**Open Questions:** none beyond those in `safe_join`.
