## `has_link_component` in sgit_ai/storage/Vault__Path_Guard.py (L153-L164)

```python
# L156-L164
rel = os.path.relpath(full, base_abs)
if rel in ('.', ''):
    return False
path = base_abs
for part in rel.split(os.sep):
    path = os.path.join(path, part)
    if os.path.islink(path):
        return True
return False
```

**Purpose:** True when `full` or any directory between `base_abs` and `full` is a symlink (links above `base_abs` are not checked, L154-L155). The in-tree half of the "never writes/reads through a link" rule.

**Inputs & Assumptions:**
- `base_abs` (str): absolute containment root. Trust: trusted. Precondition: already absolute (callers pass `os.path.abspath(...)`: `safe_join` L140, `Vault__Sub_Tree.py:L42,L48`, `Vault__Secret_Guard.py:L39,L48`, `Vault__Sync__Commit.py:L100`).
- `full` (str): absolute candidate. Precondition: lexically under `base_abs` — if not, `relpath` yields `../…` and the walk would `islink` paths outside the base; callers establish containment first (`safe_join` L142 before L145; the other three callers build `full` from `base + rel_path` where `rel_path` came from an `os.walk` of the base).
- Implicit: live filesystem.

**Outputs & Effects:** Pure read of the filesystem; bool; `os.path.islink` returns False for missing paths, so a non-existent leaf passes.

**Block-by-Block:**
- L156-L158: `relpath`, with `.`/`''` meaning `full == base_abs` → no components → False.
- L159-L163: prefix walk with `islink` on each. **Assumes** `os.sep` is the only separator in `full` — true after `abspath` on POSIX; on Windows `abspath` normalises `/` to `\`. Splitting on `os.sep` only means a `\` inside a POSIX filename stays part of one component, consistent with `safe_join` L141.
- Not a junction check: `is_link` (L172-L181) adds `os.path.isjunction` for Python 3.12+, but **this function uses `islink` only**, so a Windows junction as a directory component is not detected here. `nothing found` that a caller compensates (documented Windows scope in threat model §5 is about modes, not junctions).

**Cross-Function Dependencies:**
- Callers: `safe_join` L145 (writes); `Vault__Sub_Tree.make_entry` L48 (commit-time read: a tracked path under a link keeps its committed entry, L49-L50); `Vault__Secret_Guard.refuse_files` L48 (skips links/under-links before any open); `Vault__Sync__Commit` L100 (sparse commit path).
- Tests: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::Test_Fixed__Symlinks` (`test_a_link_out_of_the_tree_is_never_committed`, `test_a_write_through_a_symlinked_folder_is_refused`, `test_a_tracked_file_replaced_by_a_link_keeps_its_committed_version`).

**Open Questions:**
- Junction directories on Windows (see above).
