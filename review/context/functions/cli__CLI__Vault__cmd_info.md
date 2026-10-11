## `cmd_info` in sgit_ai/cli/CLI__Vault.py (L1704-L1804)

**Purpose:** `sgit vault info`: print identity, remote, branch status and web URL. It is the command that prints the **most key material**: vault key, passphrase, read key (full clone), or read key (read-only clone), plus a web URL that embeds the bare vault key.

**Inputs & Assumptions:**
- `args.directory` (default `.`), `args.base_url`, `args.token`, `args.transport`.
- Implicit: `clone_mode.json` (`load_clone_mode`, parse failure ⇒ `{'mode': 'full'}`), `local/vault_key` (`load_vault_key`), `local/token`, `local/base_url`.

**Outputs & Effects (stdout):**
- Read-only clone (L1712-L1731): `Vault ID`, **`Read key: sgit_private_read_<hex>`** (L1722, from `clone_mode.json`), remote URL, transport. `resolve_base_url(args.base_url, directory)` (L1718) **saves** `--base-url` to `local/base_url` when given — `info` with a flag records a server.
- Full clone (L1733-L1804): `Vault ID`, **`Passphrase`** (L1769), **`Vault key: sgit_private_vault_<passphrase>:<id>`** (L1770), **`Read key`** (L1775-L1776, derived by PBKDF2), `Write key: ✓ available` (presence only), **`Web URL: <base_url with send→vault>/en-gb/#<bare vault key>`** (L1759-L1760, L1777) — the vault key in a URL fragment, "until SG/Vault web ships prefix support". `Token: configured|not configured` (L1781; never the value). Then `sync.status(directory)` (L1787) — a network call to the pinned/recorded server for branch status.

**Block-by-Block (key handling):**

```python
# L1733-L1746
vault_key = self.token_store.load_vault_key(directory)
if not vault_key: print(...); sys.exit(1)
crypto = Vault__Crypto()
passphrase, vault_id = crypto.parse_vault_key(vault_key)
full_vault_key       = crypto.format_vault_key(vault_key)
```
- **What:** Read the key file (prefix stripped by `parse_vault_key`/`format_vault_key`).

```python
# L1748-L1760
base_url = self.token_store.resolve_base_url(getattr(args, 'base_url', None), directory) or DEFAULT_BASE_URL
web_url  = (base_url.replace('send.sgraph.ai', 'vault.sgraph.ai') + '/en-gb/#' + crypto.strip_key_prefix(vault_key))
```
- **Assumes:** `DEFAULT_BASE_URL = Vault__API().default_base_url()` (L1708) — the pinned env var at this point (`_pin_vault_server` ran; `vault info` is not in `_CREATES_VAULT`). The web URL puts the **bare vault key** after `#` — a fragment is not sent over HTTP by browsers, but it lands in terminal scrollback and anything that logs stdout.

```python
# L1786-L1787
sync   = self.create_sync(base_url, None)
status = sync.status(directory)
```
- **What:** No token passed (`None`) — the status call goes out **without** the saved token (`create_api(base_url, '')`, `_auth_headers` adds nothing when `access_token` is empty, `Vault__API.py:L84-L87`). On a server that requires the token, `status` falls back to "remote unreachable" semantics inside `Vault__Sync__Status` (not traced).

**Cross-Function Dependencies:**
- Callees: `CLI__Token_Store.load_clone_mode`, `load_vault_key`, `resolve_base_url` (writes), `load_token`; `Vault__Crypto.parse_vault_key`, `format_vault_key`, `format_read_key`, `derive_keys_from_vault_key`; `_transport_line_for`; `create_sync`; `Vault__Sync.status`.
- Callers: `vault info` parser (L573-L577).
- Tests: `tests/unit/cli/test_CLI__Vault__Commands.py::test_cmd_info_prints_vault_id`, `::test_cmd_info_no_vault_key_exits`, `::test_cmd_info_prints_version`.

**Open Questions:**
- unclear; whether `info` printing the passphrase, the full vault key and a web URL carrying the bare key is the intended "show me my credentials" surface (it overlaps `vault show-key`), or whether `info` was meant to be safe to paste into a chat/log. Threat model §2 lists "logs" as a place the vault key must not reach; this command's stdout is the obvious route.
- unclear; `resolve_base_url` persisting `--base-url` from an info command.
