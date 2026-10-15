## `should_ignore_dir` in sgit_ai/core/Vault__Ignore.py (L108-L116)

```python
# L110-L116
if Vault__Path_Guard().is_protected(rel_dir):   # structural: refused even if tracked (no grandfather) — A2
    return True
if not self._dir_matches_ignore_rule(rel_dir):
    return False
if rel_dir in self.tracked_dirs:            # tracked-wins: descend so the per-file rule can decide
    return False
return True
```

**Purpose:** Prune decision for `os.walk`: skip a directory unless (a) it is not ignored by any rule, or (b) it is ignored but holds tracked files (then descend and let `should_ignore_file` decide per file). Structural directories are pruned unconditionally.

**Inputs & Assumptions:** `rel_dir` from the walk (`f'{rel_root}/{d}'`). Implicit: `tracked_dirs` = every ancestor prefix of every tracked path (`load_tracked_paths` L87-L93).

**Outputs & Effects:** Pure bool.

**Cross-Function Dependencies:** Callees `is_protected`, `_dir_matches_ignore_rule` (L118-L124: basename in `ALWAYS_IGNORED_DIRS`, prefix in `ALWAYS_IGNORED_DIR_PREFIXES`, or `_matches(is_dir=True)`). Callers: `Vault__Sync__Base` L429, `Vault__Bare` L119, `Vault__Revert` L147, `Vault__Branch_Switch` L436/L459, `Vault__Diff` L824, `Vault__Stash` L218, `Vault__Merge` L117/L134, `Vault__Sync__Push` L979. Note `Vault__Merge.remove_conflict_files` L116 and `Vault__Bare` L118 also exclude `.sg_vault` explicitly — redundant with `is_protected`.

Not a link check: a symlinked directory is handled by the callers (`Vault__Sync__Base` L430-L432 removes link dirs from `dirs`; `os.walk(followlinks=False)` never descends into them anyway).

**Open Questions:** none.
