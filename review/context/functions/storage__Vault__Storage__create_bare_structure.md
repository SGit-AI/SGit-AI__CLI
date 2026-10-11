## `create_bare_structure` in sgit_ai/storage/Vault__Storage.py (L69-L81)

```python
# L70-L81
sg_dir = self.sg_vault_dir(directory)
for sub_dir in [self.bare_data_dir(directory), ..., self.local_dir(directory)]:
    os.makedirs(sub_dir, exist_ok=True)
return sg_dir
```

**Purpose:** Lays out `.sg_vault/bare/{data,refs,keys,indexes,pending,branches,cache/value,cache/pointer}` and `.sg_vault/local` for a new vault or clone.

**Inputs & Assumptions:** `directory` trusted (user's). Implicit: umask — directories are created with default mode (threat model §5: "directories are 0755 (names visible)"). `exist_ok=True` means a pre-existing `.sg_vault` (or a symlink named `.sg_vault` pointing elsewhere — `makedirs` follows it if it is a directory link) is accepted silently. `nothing found` that any caller checks `.sg_vault` is not a symlink before this call; `Vault__Sync.init` L52 does `os.makedirs(directory, exist_ok=True)` first and `Step__Clone__Check_Directory.py:L24` calls after its own emptiness check.

**Outputs & Effects:** Creates directories; returns `sg_dir`.

**Cross-Function Dependencies:** Callers `Vault__Sync.init` L62, `Step__Clone__Check_Directory` L24. Test `tests/unit/sync/test_Vault__Storage.py::test_create_bare_structure`.

**Open Questions:**
- Behaviour when `<directory>/.sg_vault` already exists as a symlink (A6 pre-plants it): `makedirs(exist_ok=True)` succeeds and all later writes (`write_private`, object store) land at the link's target. Nothing in this slice checks it.
