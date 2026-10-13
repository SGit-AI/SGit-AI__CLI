## `find_vault_root` in sgit_ai/storage/Vault__Storage.py (L86-L96)

```python
# L89-L96
path = os.path.abspath(directory)
while True:
    if os.path.isdir(os.path.join(path, SG_VAULT_DIR)): return path
    parent = os.path.dirname(path)
    if parent == path: return os.path.abspath(directory)
    path = parent
```

**Purpose:** git-style discovery: walk up from `directory` to the nearest ancestor holding `.sg_vault`; otherwise return the original absolute path.

**Inputs & Assumptions:** `directory` trusted (argv). Implicit: the filesystem above the cwd — any ancestor's `.sg_vault` is accepted, including one under a shared parent (e.g. `/tmp/.sg_vault`, `/home/.sg_vault`) that another local user created (A6). `isdir` follows symlinks.

**Outputs & Effects:** Pure read; returns an absolute path.

**Cross-Function Dependencies:**
- Caller `CLI__Main` L995, only when `<directory>/.sg_vault` is not already present (L994), and only to rewrite `args.directory` (L996-L997). `CLI__Serve._find_vault_root` L116 is a separate implementation (not read).
- Tests: `tests/unit/sync/test_Vault__Storage.py::Test_Vault__Storage__Find_Vault_Root` including `test_find_vault_root__does_not_escape_vault`.

**Open Questions:**
- Whether `CLI__Main` has a ceiling (home directory, filesystem boundary) for the walk — none in this function; `CLI__Main.py:L988-L997` applies the result unconditionally. The A6 row of the threat model ("plant files") is the relevant context.
