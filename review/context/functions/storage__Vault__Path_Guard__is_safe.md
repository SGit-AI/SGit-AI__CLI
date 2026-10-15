## `is_safe` in sgit_ai/storage/Vault__Path_Guard.py (L81-L87)

```python
# L83-L87
try:
    self.safe_join(base_dir, rel_path)
    return True
except Vault__Unsafe_Path_Error:
    return False
```

**Purpose:** Boolean mirror of `safe_join`; "never raises" (docstring L82).

**Inputs & Assumptions:** as `safe_join`. Only `Vault__Unsafe_Path_Error` is caught; an `OSError` from `os.path.realpath`/`islink` inside `safe_join` would propagate — those stdlib calls do not raise on missing paths, so in practice none is expected; `nothing found` that any test exercises an `OSError` here.

**Outputs & Effects:** Pure bool; the filesystem is read (via `has_link_component`/`realpath`).

**Cross-Function Dependencies:**
- Callee `safe_join` L115 (internal).
- Callers: `is_writable` L79 only (no other direct caller in `sgit_ai/`; `tests/unit/storage/test_Vault__Path_Guard.py::test_is_safe__*` exercise it).

**Open Questions:** none.
