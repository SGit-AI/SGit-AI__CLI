## `message` in sgit_ai/core/actions/pull/Vault__Pull__Guard.py (L96-L102)

**Purpose:** Formats the `blocked` list as the `Vault__Dirty_Working_Tree_Error` text: one line per path with its reason, then the remedy (`sgit commit` or `sgit vault stash`) and "nothing was changed".

**Inputs & Assumptions:** `blocked` — list of `(path, reason)`; paths are working-copy relative paths from the scan (user's own file names).

**Outputs & Effects:** str; no effects. Printed by `CLI__Main._print_friendly_error` L1035.

**Cross-Function Dependencies:** caller `Step__Pull__Merge._guard_working_tree` L292. Test: `test_Pull__Dirty_Working_Tree.py::test_message_names_paths_and_remedy`.

**Open Questions:** none.
