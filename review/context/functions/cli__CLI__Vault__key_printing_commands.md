## `cmd_vault_show_key` in sgit_ai/cli/CLI__Vault.py (L1689-L1702)

**Purpose:** Print the vault key (as stored, i.e. prefixed form since 0.21 writes `sgit_private_vault_…`) and the vault id for the vault in `directory`. Exit 1 when no key file. No network.

**Prints:** `Vault key:  {vault_key}` (L1699) — full secret to stdout. Tests: `tests/unit/cli/test_CLI__Vault__Commands.py::test_cmd_vault_show_key_prints_key`, `::test_cmd_vault_show_key_no_key_exits`.

---

## `cmd_vault_show` in sgit_ai/cli/CLI__Vault.py (L1681-L1687)

**Purpose:** Print the vault key stored under an alias in the encrypted credential store, after a `getpass` passphrase prompt (`CLI__Credential_Store._prompt_passphrase` L57-L64). Bare `print(vault_key)` (L1684) — meant for piping.

---

## `cmd_vault_add` in sgit_ai/cli/CLI__Vault.py (L1658-L1662)

**Purpose:** Store a vault key under an alias: passphrase via `getpass` (confirmed), the key from `--vault-key` **or** `getpass.getpass('Vault key: ')` (L1660) — so the key need not be in argv. Written by `CLI__Credential_Store.add_vault` (out of slice; TM-R11 notes one global salt).

---

## `cmd_derive_keys` in sgit_ai/cli/CLI__Vault.py (L2166-L2191)

**Purpose:** Plumbing: from a vault key (or `read_key:vault_id`) print `vault_id`, **`read_key`** (bare hex), **`write_key`** (bare hex, L2188), `ref_file_id`, `branch_index_file_id`. The only command that prints the **write key**. Input is argv (`vault_key` positional, L687-L694); no stdin form.

**Assumes:** the caller is a script that wants bare hex (comment L2169-L2173). Context-free (`_CONTEXT_FREE_VAULT_SUBS`, `CLI__Main.py:L978`), so it works outside a vault.

---

## `cmd_init` in sgit_ai/cli/CLI__Vault.py (L328-L405)

**In-slice behaviour:** after `sync.init(...)`: saves `--token` if given (L369-L371), **always records the server** (`args.base_url or Vault__API().default_base_url()` → `save_base_url`, L372-L373; "an environment variable must never redirect it later") — note `init` is in `_CREATES_VAULT`, so the env var *is* honoured here and then frozen into the vault. Prints **`Vault key: {result["vault_key"]}`** (L377) — the new secret to stdout, with "Save your vault key" advice. Test: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_init_records_the_server_it_used`.

---

## `cmd_vault_move` in sgit_ai/cli/CLI__Vault.py (L582-L774)

**In-slice behaviour:** `--new-key` from argv (L590) or auto-generated (L638-L644, 24 lowercase+digit passphrase, 8-char id) or typed at a prompt (L681-L686); prints the new key **before** the move in the confirmation screen (L659) and **after** it (L761, prefixed); `--to`/prompt for the target API URL (L591, L706-L711); `resolve_base_url(target_api_url or api_url_now, directory)` **saves** the target URL to `local/base_url` (L736-L737) before `sync.move`; token from `--token` or stored (L599, L613); the sync is built with explicit `base_url`/`access_token` (L738-L740) — not through `create_api`, so no `debug_log` and no `Vault__API__Auto`. Reads `config.json` for `vault_id`/`api_url` (L629-L633) — fields `Schema__Local_Config` does not define (L53-L65 of the schema), so `api_url_now` is normally `''` → `default_base_url()`.

---

## `cmd_rekey` / `cmd_rekey_init` in sgit_ai/cli/CLI__Vault.py (L2000-L2086, L2129-L2149)

**In-slice behaviour:** `--new-key` from argv; the new key printed to stdout (L2082, L2145) and, with `--json`, as `{"vault_key": …}` (L2068-L2070). `create_sync()` with no arguments (L2010, L2134) ⇒ the pinned default server.

---

## `cmd_backup` in sgit_ai/cli/CLI__Vault.py (L433-L487)

**In-slice behaviour:** `--include-key` embeds `local/vault_key` as `VAULT-KEY` in the zip (`Vault__Backup.py:L127-L130`; with the signing `.pem` files too, L133) after a y/N prompt unless `--yes` (L452-L463). Warns when the work tree is a git repo whose `.gitignore` does not exclude `.sg_vault/backups/` (L440-L447). The zip name is `.vault__*.zip`, which `Vault__Path_Guard` protects and `Vault__Secret_Guard` refuses by content (so a backup cannot be committed into the vault: `test_Security__Fixed__Secrets_In_Commits.py::test_commit_after_restore_does_not_commit_the_backup`, `::test_a_renamed_backup_is_refused_by_content`).

---

## `cmd_restore` in sgit_ai/cli/CLI__Vault.py (L509-L581)

**In-slice behaviour:** `--key` from argv (L514); when the zip has no key and mode is `expanded`, offers a `CLI__Input().prompt` to paste the key (L556-L564; visible echo, TTY only, 30 s timeout). Nothing printed back.

---

## `cmd_vault_attach` in sgit_ai/cli/CLI__Vault.py (L1587-L1607)

**In-slice behaviour:** `--vault-key` or `--read-key`+`--vault-id` from argv → `Vault__Attach.attach` (verifies the derived ref id exists in `bare/refs` before writing, `Vault__Attach.py` grep L55-L60 — "Nothing written" on failure; writes `vault_key` or `clone_mode.json`, removing the stale other); then `save_base_url`/`save_token` when flags given (L1600-L1604). Prints ids only.

---

## `_read_key_or_exit` in sgit_ai/cli/CLI__Vault.py (L2221-L2233)

**Purpose:** For local inspect/history commands: `CLI__Token_Store.resolve_read_key(args)` — `--vault-key` (any prefixed form or the `{64-hex}:{id}` shorthand) else the clone's `vault_key` else the read key in `clone_mode.json` (L205-L224 of Token_Store). Exit 1 with guidance when none; prints the `ValueError` text for a declared read key that does not parse (the message is fixed text, `read_key_from_credential` L240).
