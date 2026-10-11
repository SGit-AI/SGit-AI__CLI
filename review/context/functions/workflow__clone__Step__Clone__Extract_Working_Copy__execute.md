## `execute` / `_refuse_incomplete` in sgit_ai/workflow/clone/Step__Clone__Extract_Working_Copy.py (L14-L45, L47-L60)

**Purpose:** HEAD checkout into the working copy; a HEAD file with no (verified) object fails the whole clone rather than leaving a working copy that reads as "that file deleted" (which the next commit would propagate, docstring L48-L50).

**Inputs & Assumptions:** `named_commit_id`, `sparse`, `bare`, `scope_paths`; objects already local and verified.

**Outputs & Effects:**
- Scoped clone: `Vault__Scoped_Tree.flatten` → `missing` computed from `obj_store.exists` (L34) → `_refuse_incomplete` → `_checkout_flat_map` (L36; per-path `is_protected` + `safe_join`, `Vault__Sync__Base.py:L511-L518`).
- Full clone: `Vault__Sub_Tree.checkout(directory, tree_id, read_key, missing=missing)` (L39; per-entry `is_protected` L188-L192 and `safe_join` L193 of Sub_Tree; a missing blob is appended to `missing` instead of warned, L200-L202) → `_refuse_incomplete` (L40) — note the order: files are written **first**, then the clone is refused if any were missing. The refusal message says "The directory is not a usable clone (no key was written)" (L57) — true, since `Setup_Local_Config` runs after; the partially written working copy remains on disk.
- Sparse or bare: no checkout.

**Assumes:** tree entry names are attacker-influenced (author A5) and contained by `Vault__Path_Guard` (threat model §5 Path guard row). Decrypted plaintext is written with `open(..., 'wb')` and default umask (no mode control for working-copy files — threat model §5 File modes: directories 0755).

**Cross-Function Dependencies:** callee `Vault__Sub_Tree.checkout` (L168-L212), `_checkout_flat_map`; caller `Workflow__Clone` step 11 / `__ReadOnly` step 10, after verify and (full) after create-branch.

**Open Questions:**
- unclear; whether a refused-incomplete full clone should remove what `checkout` already wrote (the directory is left with files and no `.sg_vault/local` key; `cmd_clone`'s `Directory is not empty` recovery would then trigger on retry — `_offer_clone_recovery` L83-L130).
