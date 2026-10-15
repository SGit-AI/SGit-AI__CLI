## `clone` in sgit_ai/core/actions/clone/Vault__Sync__Clone.py (L8-L16)

Delegates to `_clone_with_keys` with the same arguments. No logic.

---

## `_run_clone_workflow` in sgit_ai/core/actions/clone/Vault__Sync__Clone.py (L44-L66)

**Purpose:** Runs the workflow; translates a `FileNotFoundError` that names an object the integrity check refused into `Vault__Integrity_Error` (`_integrity_error_for`, L68-L83); in `finally`, prints the refusal summary (`_warn_integrity_fallbacks`, to the progress callback or stderr) and removes the temp workspace root (L62-L66).

**Assumes:** `ws.integrity_failures` is the list `Clone__Workspace.save_file` appends to (L67 of Clone__Workspace). The summary never includes key material (file ids only).

**Callers:** `_clone_with_keys` L111, `clone_read_only` L172, `clone_branch` L207, `clone_headless` L243, `clone_range` L280.

---

## Not analyzed (out of slice): `_warn_integrity_fallbacks` (L18-L37), `_progress_to_stderr` (L39-L42), `_integrity_error_for` (L68-L83), `_normalised_scope` (L139-L141), `clone_branch` (L183-L218), `clone_headless` (L220-L250), `clone_range` (L252-L292), `_download_blobs_by_id` (L294-L349), `_clone_download_blobs` (L351-L435).

Notes for the index: `clone_branch`/`clone_range` run `Workflow__Clone__Branch`/`__Range` which include the verify step (`test_K3__every_clone_entry_point_checks_signatures`); `clone_headless` runs `Step__Clone__Headless__Setup_Config` (L16-L44), which writes `local/vault_key` (0600, L40-L41) and a `config.json` with `my_branch_id=''`, `sparse=True`, and **no `last_remote_head`** — a headless clone has no baseline, so its first pull has nothing to compare (rewind guard: `last_known=''` → FORWARD). `_download_blobs_by_id`/`_clone_download_blobs` write through the `save_file` callback passed by the step (verified).
