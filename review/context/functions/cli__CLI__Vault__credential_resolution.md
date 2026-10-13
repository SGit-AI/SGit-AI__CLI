## `_resolve_clone_credential` in sgit_ai/cli/CLI__Vault.py (L159-L206)

**Purpose:** `(vault_key, read_key, shorthand_detected)` from the positional and `--read-key`. Declaration beats heuristic: a `sgit_private_vault_` prefix disables the `{64-hex}:{id}` read-key shorthand; a declared read key that does not parse is an error, never retried as a passphrase (docstring L162-L175).

**Block-by-Block:**
- L180-L188: `classify_key` by prefix (`Vault__Crypto.py:L86-L103`: `sgit_public_read_` → READ_PUBLIC, `sgit_private_read_`/legacy → READ_PRIVATE, `sgit_private_vault_`/legacy → VAULT, else UNKNOWN); `strip_key_prefix` on both inputs.
- L190-L198: shorthand: unknown kind, no `--read-key`, `head:tail` with `head` 64 lowercase hex and `tail` `[a-zA-Z0-9_-]+` ⇒ read-only clone of `tail`. **A bare 64-hex passphrase vault key is misrouted** unless prefixed (the docstring says exactly this is why the prefix exists).
- L200-L205: declared read key without a parsed read key ⇒ `ValueError` with fixed text.

**Assumes:** `tail` regex allows uppercase and `_`, which `parse_vault_key`'s `VAULT_ID_PATTERN` (4-24 lowercase alnum) would reject for a vault key; here it only names a vault id for the RO path (`Safe_Str__Vault_Id` on `Schema__Clone__State` validates later).

**Callers:** `cmd_clone` L220-L221.

---

## `_warn_private_key_over_plain_http` in sgit_ai/cli/CLI__Vault.py (L142-L157)

**Purpose:** stderr warning when a non-public key is used with an explicit `http://` base URL (SP-6 CLI half). `sgit_public_read_` exempt. No effect on behaviour (TM-R10: plain http accepted, `tests/security/test_Security__Known_Gaps.py::test_TM_R10__plain_http_base_url_is_accepted`).

**Assumes:** `base_url` is the flag value; see `cmd_clone` record for the env-var gap.

---

## `create_sync` / `create_api` in sgit_ai/cli/CLI__Vault.py (L34-L38, L40-L60)

**Purpose:** Build the API client: `api` → `Vault__API`; `static`/`local` → `Vault__API__Static` (no token); `auto` (default) → `Vault__API__Auto` with `base_url or ''` and `access_token or ''`, `tls_verify`, `debug_log=self.debug_log`. `create_sync` calls `api.setup()` (fills `base_url` from `default_base_url()` when empty, `Vault__API.py:L32-L35`).

**Where the token goes:** `Safe_Str__Access_Token` field; sent as `x-sgraph-access-token` and `X-API-Key` on every request (`_auth_headers` L78-L90); masked in error text (L477-L482); never logged by `CLI__Debug_Log`. Redirects are not followed on the pooled path (`_send` L434-L436), so the token is not replayed to another host; `fetch_presigned` follows redirects but sends **no** auth headers (plain `urllib` opener, L42-L56) and re-checks each hop (L46-L49).

**Callers:** nearly every network command; `cmd_vault_move` bypasses it (explicit `Vault__API(...)`, L738-L740).

---

## `_offer_clone_recovery` in sgit_ai/cli/CLI__Vault.py (L83-L130)

**Purpose:** When the target directory is not empty: show the effective remote, offer (TTY only) a new URL and directory, re-run the clone with `self.token_store.load_token('.')` (L117 — the token file of the **current working directory's** vault, if any), then `save_base_url(new_url, result['directory'])` (L124-L125). Prints vault id / HEAD; not the key.

**Assumes:** the retry URL typed at the prompt is trusted as the server for the new clone; `_warn_private_key_over_plain_http` is **not** called on this path.

---

## `_prompt_remote_setup` in sgit_ai/cli/CLI__Vault.py (L1255-L1328)

**Purpose:** First-push interactive setup: URL (default `Vault__API().default_base_url()` — pinned value), token typed via `CLI__Input().prompt` (echoed, L1284), health-checked with `CLI__Doctor.run_subset` against `Doctor__Context(url, token, vault_id derived from the stored vault key, tls_verify=True)` (L1295-L1310); on success `save_token` + `save_base_url` (L1323-L1324). Aborts on non-TTY or any failed check ("Token not saved").

**Assumes:** the health check sends the token to the URL the user typed before anything is saved — by design (it is how the URL is validated).

---

## `cmd_remote_add` / `cmd_remote_set_url` / `cmd_remote_show` in sgit_ai/cli/CLI__Vault.py (L1362-L1395, L1434-L1471, L1415-L1432)

- `remote add`: `vault_id` from argv or derived from the stored vault key (L1365-L1369); unless `--no-health-check`, `CLI__Doctor.run_subset` with the **stored token** against `args.url` (L1377-L1383) — the token is sent to the new URL before it is recorded; then `Vault__Remote_Manager.add_remote` (plain-mode `remotes.json`). `remote` commands are exempt from the server pin (`_pin_vault_server` L911-L912), so this is the sanctioned way to point a vault at a new host (`test_both_remedies_the_refusal_names_work_as_written[remote]`).
- `remote set-url`: same health check against `new_url` with the stored token (L1444-L1462) unless `--no-health-check`.
- `remote show`: token printed **redacted** as `***...(N chars)` (L1424).

---

## `cmd_check_verify` in sgit_ai/cli/CLI__Vault.py (L1806-L1826)

**Purpose:** `sgit check verify`: `resolve_token`/`resolve_base_url` (both **save** flag values to the vault), `create_sync`, `Vault__Sync.verify_signatures` (`Vault__Sync.py:L257-L272`: this clone's own head, boundaries from config, key pre-fetch, `verify_chain` with no `stop_at`); prints counts; exit 1 when any `bad`. Advisory: it never writes a ref or baseline. `tests/unit/review/test_Signature_Policy_And_Rewind__Fixes.py::test_check_verify_fetches_a_teammates_key`.

---

## `setup_credential_store` (L1655-L1656): `self.credential_store.setup(sg_send_dir)` — called by `run` for every `vault` command (L833).
