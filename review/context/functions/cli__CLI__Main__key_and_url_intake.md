## `build_parser` in sgit_ai/cli/CLI__Main.py (L119-L442) — the argv surface for keys, tokens and servers (in-slice portion only)

**Purpose:** Where a key, read key, token or server address can enter from argv. The rest of the parser (command plumbing) is out of slice.

**Secret-bearing arguments defined here:**
- Global `--base-url` (L133), `--token` (L134); per-command `network_args` `--base-url` (L148), `--token` (L150), `--transport`, `--verify-tls/--no-verify-tls` (L156-L163).
- `clone vault_key` positional (L201-L205; `-` = stdin), `--read-key HEX` (L212-L215).
- `init --vault-key` (L225), `create --vault-key` (L235).
- `clone-branch vault_key` (L247), `clone-headless vault_key` (L256), `clone-range vault_key` (L263) — all accept `-` via `_KEY_FROM_STDIN`.
- `vault add --vault-key` (L510; `getpass` when omitted), `vault attach --vault-key/--read-key/--vault-id` (L517-L520), `vault backup --include-key` (L527), `vault format --token/--base-url` (L569-L570), `vault info --token/--base-url` (L575-L576), `vault move --new-key`, `--to`, `--token` (L617-L628), `vault rekey --new-key` (L633), `rekey init --new-key` (L653), `vault restore --key` (L662), `vault show-key` (L684), `vault derive-keys vault_key` (L687-L694).
- `remote add url`, `remote set-url new_url` (L452-L453, L475-L476).

**Assumes:** argparse leaves these values in `sys.argv` and process memory; nothing here scrubs them. `--token` on `format`/`info`/`move` is defined again locally (not via `network_args`), with `default=None`, so `resolve_token(None, directory)` falls back to the stored token.

**Cross-Function Dependencies:** consumed by the `CLI__Vault` records below and by `_cmd_clone_*`.

---

## `_key_from_stdin` in sgit_ai/cli/CLI__Main.py (L1223-L1230)

**Purpose:** `sgit clone - <dir>`: `sys.stdin.readline().strip()`; empty ⇒ error exit 1. The key never appears in argv, `ps` or shell history (docstring).

**Assumes:** stdin is the key source (a pipe/redirect); when stdin is a TTY the user types it visibly (no `getpass`). The value is then handled exactly like an argv key (`args.vault_key`).

---

## `_clone_family_sync` / `_cmd_clone_branch` / `_cmd_clone_headless` / `_cmd_clone_range` in sgit_ai/cli/CLI__Main.py (L1125-L1134, L1136-L1157, L1159-L1180, L1182-L1221)

**Purpose:** The thin-clone commands: resolve token (`resolve_token(args.token, None)` — **not saved**, no directory), `--base-url`, TLS flag and transport, build the sync (`CLI__Vault.create_sync`), strip the key prefix (`Vault__Crypto.strip_key_prefix`), default the directory to the vault_id half of the key (`vault_key.split(':')[-1]`), run the clone, print directory / vault id / HEAD.

**What reaches stdout:** `result['vault_id']`, `result['commit_id']` — not the key (the sync result dict does contain `vault_key`, `Vault__Sync__Clone.clone_branch` L213 / `clone_headless` L247 / `clone_range` L285; these commands do not print it).

**What reaches disk:** via the workflows — `clone_headless` writes `local/vault_key` (`Step__Clone__Headless__Setup_Config`); none of the three saves the token or base URL (contrast `cmd_clone` L253-L254, L302-L305) — so a later command on such a clone has no recorded server and hits `_pin_vault_server`'s unrecorded-vault branch (the docstring of `_pin_vault_server` L902-L903 names clone-branch / clone-headless as exactly that case).

**Open Questions:**
- unclear; the token given to a thin clone is used for that clone only and not persisted — intended asymmetry with `cmd_clone`?

---

## `_setup_debug` in sgit_ai/cli/CLI__Main.py (L1069-L1078)

See `run` record: enables `CLI__Debug_Log` (URL path, status, sizes; no headers). `_load_debug_flag` (L1080-L1085) reads `.sg_vault/local/debug`.

---

## `_print_friendly_error` in sgit_ai/cli/CLI__Main.py (L1010-L1067)

**Purpose:** Map exceptions to one-line `error:` messages. Refusals (`Vault__Signature_Error`, `Vault__Ref_Rewind_Error`, `Vault__Dirty_Working_Tree_Error`, `Vault__Unreadable_Ref_Error`, `Vault__Secret_In_Commit_Error`, `Vault__Unsafe_Path_Error`, …) print `str(error)` only (L1027-L1035). Other types print a classified line plus the last traceback frame location (L1060-L1066).

**Assumes:** none of those messages carries key material — they name commit ids, paths, ref ids, server URLs. `Vault__Unsafe_Path_Error` echoes the offending **path** (`Vault__Path_Guard.py:L129-L150`), author-chosen text printed to the terminal (control characters not stripped).

---

## Accessors: `_unpin_vault_server` (L945-L950): restore or `pop` the env var. `_context_free_subcommand` (L980-L982): `vault derive-keys|serve|mirror` skip the inside gate. `_resolve_vault_dir` (L984-L997): walk up from `args.directory` unless the command is in `_NO_WALK_UP`. `_detect_context` (L1268-L1272): `Vault__Context.detect_with_override(cwd, args.vault)`.

---

## Not analyzed (out of slice): `_check_ssl_error` (L48-L83), `_read_version` (L85-L90), `cmd_reference` (L92-L108), `cmd_update` (L110-L117), `_add_remote_subtree` (L444-L448), `_add_remote_subtree_to` (L450-L501), `_register_vault_ns` (L503-L712, beyond the argument list above), `_register_cache` (L714-L745), `_register_migrate` (L747-L764), `_register_pki` (L766-L820), `_partial_scope_of` (L999-L1008), `_load_debug_flag` (L1080-L1085), `_save_debug_flag` (L1087-L1097), `_cmd_log_dispatch` (L1099-L1106), `_cmd_debug_on/off/status` (L1108-L1123), `_exit_if_moved_command` (L1232-L1252), `_first_positional` (L1254-L1266), `_cmd_wrong_context` (L1274-L1295), `_cmd_help` (L1297-L1319).
