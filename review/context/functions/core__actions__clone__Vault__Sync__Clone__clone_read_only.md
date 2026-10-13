## `clone_read_only` in sgit_ai/core/actions/clone/Vault__Sync__Clone.py (L143-L181)

**Purpose:** Clone with a read key only (`Workflow__Clone__ReadOnly`, 11 steps, `Workflow__Clone__ReadOnly.py:L23-L35`): same download, verify and checkout steps as the full clone, but no clone branch, and the credentials written are `clone_mode.json` (holding the **read key** in plaintext JSON, 0600) instead of `vault_key`.

**Inputs & Assumptions:**
- `vault_id` (str), `read_key_hex` (str): from the CLI (`_resolve_clone_credential`). Trust: user input; the read key is a secret unless it was a `sgit_public_read_` key.
- Implicit: `self.api`.

**Outputs & Effects:**
- `Step__Clone__ReadOnly__Set_Keys` (L13-L29): `import_read_key` derives `branch_index_file_id` (HMAC of the read key; `Vault__Crypto.py:L223-L234`), `write_key=''`.
- Steps as the full clone through `Step__Clone__Verify_Signatures` and `Step__Clone__Extract_Working_Copy`.
- `Step__Clone__ReadOnly__Setup_Config` (L24-L55): `clone_mode.json` = `{mode: read-only, vault_id, read_key, branch_name: 'current'}` via `write_private` (0600; L37-L42; `Schema__Clone_Mode.read_key` is `Safe_Str__Write_Key`, 64-hex validation, `Schema__Clone_Mode.py:L80`), then `config.json` with `my_branch_id=None`, `mode=READ_ONLY`, `last_remote_head=named_commit_id` (L46-L53).
- Returns a dict without the key (L174-L181).

**Order:** verify (step 9) precedes extract (10) and config (11), as in the full clone; the read key reaches disk only after the policy passed and the checkout completed.

**Cross-Function Dependencies:**
- Callers: `Vault__Sync.clone_read_only` (L385+) ← `CLI__Vault.cmd_clone` L250-L251 (then `save_token` / `save_base_url` L253-L254).
- Shared: `Clone__Workspace.save_file` for every object (verified).
- Tests: `test_TM_R05__read_only_clone_refuses_a_rollback` (clones RO then pulls), `test_clone_and_read_only_clone_write_their_keys_owner_only`.

**Open Questions:**
- same workspace-persistence question as `_clone_with_keys` (`read_key_hex` is in the state).
