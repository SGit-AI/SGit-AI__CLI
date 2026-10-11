## `execute` in sgit_ai/workflow/clone/Step__Clone__Headless__Setup_Config.py (L16-L44)

**Purpose:** Credentials-only clone: write `config.json` (`my_branch_id=''`, `sparse=True`, no `last_remote_head`) and `local/vault_key` (prefixed, 0600 via `write_private`, L40-L41). No `bare/` data, no index, no branch.

**Assumes:** the directory is created with default mode (L24, L35: `os.makedirs`). No server contact, so no policy check and no baseline — the first `pull` from such a clone has `last_known=''`.

**Callers:** `Workflow__Clone__Headless` (not read) ← `Vault__Sync__Clone.clone_headless` L220-L250 ← `CLI__Main._cmd_clone_headless` L1159-L1180.

**Open Questions:** none.
