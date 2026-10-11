## `is_inside` in sgit_ai/storage/Vault__Path_Guard.py (L166-L170)

```python
# L169-L170
base_real = os.path.realpath(base_dir)
return real_path == base_real or real_path.startswith(base_real.rstrip(os.sep) + os.sep)
```

**Purpose:** Resolved-path containment that tolerates a symlinked base (`/tmp -> /private/tmp`, L168).

**Inputs & Assumptions:** `base_dir` trusted; `real_path` must already be `realpath`'d by the caller (docstring L167; `safe_join` L148 does so). If a caller passed an unresolved path the comparison would be lexical only — only one caller exists and it resolves.

**Outputs & Effects:** Pure; bool.

**Cross-Function Dependencies:** Caller `safe_join` L148 only. No other callers in `sgit_ai/` (`CLI__Main.py:L863,L915,L1285` call a different `context.is_inside()`).

**Open Questions:** none.
