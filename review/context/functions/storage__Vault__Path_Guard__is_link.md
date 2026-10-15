## `is_link` in sgit_ai/storage/Vault__Path_Guard.py (L172-L181)

```python
# L178-L181
if os.path.islink(full_path):
    return True
is_junction = getattr(os.path, 'isjunction', None)        # Python 3.12+
return bool(is_junction and is_junction(full_path))
```

**Purpose:** The scan-side predicate: every working-copy walk drops symlinks (and Windows junctions on 3.12+) so a link to `~/.ssh/id_rsa` or to `.sg_vault/local/vault_key` is never read into a blob (docstring L173-L177; threat model §5 "Symlinks").

**Inputs & Assumptions:** `full_path` (str) from an `os.walk` of the working copy. Trust: the *name* is filesystem-derived (A6 can plant it). Implicit: live filesystem. `os.path.isjunction` exists only on 3.12+ (project floor is 3.11, CLAUDE.md), so junctions are undetected on 3.11.

**Outputs & Effects:** Pure read; bool; never raises (`islink` returns False on missing paths).

**Cross-Function Dependencies:**
- Callers (each filters a walk): `Vault__Sync__Base._scan_local_directory` L430 (dirs), L438 (files); `_linked_tracked_paths` L494, L496; `Vault__Bare._list_working_copy_files` L113; `Vault__Stash` L213; `Vault__Revert._scan_working_files` L142; `Vault__Branch_Switch` L431, L454; `Vault__Diff` L819; `read_regular` L210 (post-`EL OOP` classification).
- Pairing: a filtered-out link is *not* enough on its own: the file could be swapped for a link after the filter — `read_regular`'s `O_NOFOLLOW` (L204-L206) is what closes that for reads.
- Tests: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_a_link_out_of_the_tree_is_never_committed`, `::test_K1__a_link_to_the_vault_key_is_never_committed`.

**Open Questions:**
- Behaviour on Python 3.11 for junctions (none; the threat model does not claim Windows junction coverage).
