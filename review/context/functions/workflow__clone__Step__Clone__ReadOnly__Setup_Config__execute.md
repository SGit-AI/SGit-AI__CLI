## `execute` in sgit_ai/workflow/clone/Step__Clone__ReadOnly__Setup_Config.py (L24-L55)

**Purpose:** Last step of the read-only clone: write `clone_mode.json` (mode, vault_id, **read key hex**, tracked branch name) and `config.json`.

**Outputs & Effects:** both via `write_private` / `write_local_config` → `Vault__Secret_File` (0600). `config.json`: `my_branch_id=None`, `mode=READ_ONLY`, `last_remote_head=named_commit_id` (first baseline). No `vault_key` file, no clone ref (docstring L3-L4).

**Assumes:** `read_key_hex` validated as 64-hex by `Safe_Str__Write_Key` on `Schema__Clone_Mode` (L80 of the schema) — a malformed key fails here, after the whole download; in practice `import_read_key` (`bytes.fromhex`, step 1) would have failed first.

**Readers:** `Vault__Sync__Base._read_clone_mode` (L279-L298; fail-closed on a malformed file or a READ_ONLY mode missing `read_key`/`vault_id`), `CLI__Token_Store.load_clone_mode` (L193-L203; **returns `{'mode': 'full'}` on a parse failure** — the CLI then treats a corrupt read-only clone as full for dispatch (`cmd_pull` L957-L960) and `cmd_info` (L1712-L1713), while the sync layer raises `Vault__Clone_Mode_Corrupt_Error`). `cmd_info` prints the read key from this file (L1716, L1722).

**Open Questions:** none.
