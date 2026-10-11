## `tracked_named_branch` in sgit_ai/storage/Vault__Branch_Manager.py (L111-L124)

```python
# L118-L124
clone = self.get_branch_by_id(index, str(clone_branch_id)) if clone_branch_id else None
if clone is not None and clone.creator_branch:
    named = self.get_branch_by_id(index, str(clone.creator_branch))
    if named is not None and named.branch_type == Enum__Branch_Type.NAMED:
        return named
    return None                                  # its branch is gone: never silently 'current' (S11)
return self.get_branch_by_name(index, 'current')
```

**Purpose:** Which named branch this clone's work goes to: the `creator_branch` recorded at clone/switch, else `'current'`. A recorded branch missing from the index → `None` (callers refuse by name) rather than falling back to `current` (docstring L112-L117, review S11).

**Inputs & Assumptions:** `index` (parsed, strict `Schema__Branch_Meta` list); `clone_branch_id` from local `config.my_branch_id`. If `clone_branch_id` is set but the clone branch itself is absent from the index (a host served an index without it), the code falls to L124 and returns `'current'` — the S11 refusal applies only when the clone entry exists and its creator is gone. `nothing found` that distinguishes "my clone branch vanished" from "no clone id configured" here; `Vault__Sync__Base._resolve_working_branch` L343-L346 handles the working-branch side of that case (returns `None` when `my_branch_id` is set but absent).

**Outputs & Effects:** Pure.

**Cross-Function Dependencies:** Callees `get_branch_by_id` L99-L103, `get_branch_by_name` L105-L109 (linear scans comparing `str(...)`; first match wins — duplicate names in a hostile index resolve to the earlier entry). Callers: `Vault__Sync__Push` L78, L603; `Vault__Sync__Base` L105, L268; `Vault__Sync__Status` L115; `Vault__Diff` L797; `Vault__Branch_Switch` L214; `Vault__Sync__History_Edit` L32; pull/fetch/push workflow steps.

**Open Questions:**
- The "clone id set but clone entry absent" path returning `'current'` (L124): whether a caller re-checks `config.my_branch_id` presence before trusting it.
