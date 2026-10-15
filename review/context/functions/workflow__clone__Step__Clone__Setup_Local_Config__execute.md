## `execute` in sgit_ai/workflow/clone/Step__Clone__Setup_Local_Config.py (L14-L38)

**Purpose:** Last step of the writable clone: write `config.json` and the **vault key** to `.sg_vault/local/`.

**Inputs & Assumptions:** `input.vault_key` (`Safe_Str__Vault_Key`), `clone_branch_id` (from step 10), `sparse`, `scope_paths`, `shallow_boundaries`, `named_commit_id`.

**Outputs & Effects:**
- `config.json` via `write_local_config` (`Vault__Storage.py:L133-L137` → `write_private` → `Vault__Secret_File.write`: 0600 temp, fsync, rename) with `last_remote_head = named_commit_id` (L30) — the clone's **first baseline**, in the legacy single field; the per-branch file is created on the first pull/switch (`_mark_remote_heads_file`).
- `local/vault_key` ← `crypto.format_vault_key(vault_key)` (`sgit_private_vault_…` prefix, `Vault__Crypto.py:L105-L109`) via `write_private` (L35-L36). 0600, never through a link (`Vault__Secret_File.py:L14-L35`).

**Why last:** a clone refused at verify (step 9) or extract (step 11) leaves no key on disk.

**Assumes:** `directory` is the user's chosen path; `local_config_path`/`vault_key_path` are fixed names under `.sg_vault/local/` (`Vault__Storage.py:L98-L102`).

**Cross-Function Dependencies:** readers of these files — `Vault__Sync__Base._read_vault_key` (L34-L42, also accepts the legacy `.sg_vault/VAULT-KEY`), `CLI__Token_Store.load_vault_key` (L182-L191). Tests: `test_clone_and_read_only_clone_write_their_keys_owner_only`, `test_vault_writes_key_bearing_files_owner_only`, `test_a_secret_write_never_goes_through_a_planted_link` (`tests/security/test_Security__Fixed__Symlinks_And_Local.py`).

**Open Questions:** none.
