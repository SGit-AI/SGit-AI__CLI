## `_pin_vault_server` in sgit_ai/cli/CLI__Main.py (L899-L943)

**Purpose:** Decide, once per process, which server a command run on a vault talks to, and make it the default every bare `Vault__API()` falls back to by setting `SGIT_DEFAULT_BASE_URL` for the duration of the command (review d3b8eef S1). A vault that records no server records the default on first use, **unless** the environment names another server — then it refuses rather than send the token, write key and data there.

**Inputs & Assumptions:**
- `args`: `directory`, `base_url` (global `--base-url` or per-command), `remote` (`--remote NAME`), `remote_command`, `<command>_command`.
- `command` (str); `context` (Vault__Context) with `vault_path`.
- Implicit: `os.environ['SGIT_DEFAULT_BASE_URL']`, `.sg_vault/local/remotes.json` (`Vault__Remote_Manager`), `.sg_vault/local/base_url` (`CLI__Token_Store`).

**Outputs & Effects:**
- Returns the previous env value (or `None`), or `_NO_PIN`.
- **Writes `os.environ['SGIT_DEFAULT_BASE_URL'] = server`** (L942).
- **May write `.sg_vault/local/base_url`** (L940, `store.save_base_url`, plain write + chmod 0600) — a persistent change made by a read-only-looking command such as `history log` (`test_an_unrecorded_vault_records_the_default_on_first_use`).
- May `sys.exit(1)` with the refusal message (L933-L938).

**Block-by-Block:**

```python
# L911-L912
if command in self._CREATES_VAULT or getattr(args, 'remote_command', None):
    return self._NO_PIN
```
- **What:** `init`, the clone family, `create`, `version`, `update`, `help`, `pki` and every `remote …` subcommand are not pinned (the remote commands are the remedy the refusal names, 0a0707d R2).
- **Assumes:** those commands resolve their own server: `cmd_clone` from `--base-url`/`Vault__API__Auto` default (`CLI__Vault.cmd_clone` L210-L214; `create_api` → `Vault__API().setup()` → `default_base_url()` → **the environment variable** when set). So `SGIT_DEFAULT_BASE_URL` **does** steer a clone/init/create — by design, the variable is "a self-hosted default, or a test sandbox" (`Vault__API.py:L74-L75`), and `cmd_init` then records that server (L372-L373 of CLI__Vault) so later commands are pinned to it.

```python
# L913-L917
directory = getattr(args, 'directory', None)
if not (directory and os.path.isdir(os.path.join(str(directory), SG_VAULT_DIR))):
    directory = str(context.vault_path) if context.is_inside() and context.vault_path else ''
if not directory or not os.path.isdir(os.path.join(directory, SG_VAULT_DIR)):
    return self._NO_PIN
```
- **What:** Find the vault directory: `args.directory` if it is a vault (after `_resolve_vault_dir` walked up, L843), else the detected context's root. No vault ⇒ no pin.

```python
# L918-L929
store  = self.vault.token_store
server = getattr(args, 'base_url', None) or ''
if not server:
    try:
        remote_name = getattr(args, 'remote', None); manager = Vault__Remote_Manager()
        remote = manager.get_remote(directory, remote_name) if remote_name else manager.get_default(directory)
        server = str(remote.url) if remote else ''
    except Exception: server = ''
server = server or store.load_base_url(directory)
```
- **What:** Precedence: `--base-url` flag → `--remote NAME` / default remote (`remotes.json`) → `local/base_url` file.
- **Assumes:** `remotes.json` and `base_url` are this user's files (same-user trust, A6). `Vault__Remote_Manager._save_remotes` writes `remotes.json` with plain `open('w')` and **no chmod** (`Vault__Remote_Manager.py:L119-L123`) — a URL, not a secret.
- Note: `Vault__Remote_Manager()` is constructed with no `storage` argument here (L924) — `storage : Vault__Storage` is a Type_Safe field with a default instance, so this works; `CLI__Vault._remote_mgr` passes one explicitly (L1357-L1360).

```python
# L930-L941
if not server:
    variable = (os.environ.get('SGIT_DEFAULT_BASE_URL') or '').rstrip('/')
    if variable and variable != DEFAULT_BASE_URL:
        print('error: this vault records no server, and SGIT_DEFAULT_BASE_URL=… would send its token, write key and data there. …', file=sys.stderr)
        sys.exit(1)
    server = DEFAULT_BASE_URL
    store.save_base_url(server, directory)
```
- **What:** Unrecorded vault: refuse a non-default variable; otherwise record the built-in default.
- **Assumes:** `DEFAULT_BASE_URL = 'https://dev.send.sgraph.ai'` (`Vault__API.py:L18`) is the right server for a vault that never recorded one. The comparison is exact string after `rstrip('/')`; `https://dev.send.sgraph.ai/` would pass, `HTTPS://…` would refuse.
- Tests: `tests/security/test_Security__Fixed__Server_Pin.py::test_an_unrecorded_vault_refuses_the_variable` (status/pull/push exit 1, listener sees nothing, no `base_url` written), `::test_an_unrecorded_vault_records_the_default_on_first_use`, `::test_both_remedies_the_refusal_names_work_as_written`.

```python
# L942-L943
previous = os.environ.get('SGIT_DEFAULT_BASE_URL')
os.environ['SGIT_DEFAULT_BASE_URL'] = server
return previous
```
- **Establishes:** for the rest of the command, `Vault__API().default_base_url()` == the vault's server.
- **Depended on by:** every bare `Vault__API()` (see `run` record); `CLI__Token_Store._unrecorded_server` (L108-L119) reads the same variable and now sees the pinned value; `resolve_remote` (L50-L106) also reads the files directly and may still return a *different* URL when `--base-url`/`--remote` were given (then `create_sync(remote['base_url'])` is explicit and consistent with the pin).
- Test: `::test_the_recorded_server_wins_for_every_command_including_bare_clients`, `::test_base_url_flag_still_chooses`.

**Cross-Function Dependencies:**
- Callees: `Vault__Remote_Manager.get_remote`/`get_default`, `CLI__Token_Store.load_base_url`/`save_base_url`.
- Callers: `run` L854; paired with `_unpin_vault_server` (L945-L950) in `finally`.
- Shared state: `os.environ` (process-wide; threads spawned during the command — batch_read's pool — inherit it).
- Invariant coupling: this is the mechanism behind threat model §1/§4 "the write key is a header the HOST compares": where the header goes is decided here.

**Open Questions:**
- unclear; a `--base-url` given on the command line is pinned (L919) but **not** recorded here; `CLI__Token_Store.resolve_base_url` (L23-L30) records it when the command later calls `resolve_remote`/`resolve_base_url` with a directory (e.g. `cmd_pull` L963 → `resolve_remote` → `resolve_base_url(base_url_flag, directory)` → `save_base_url`). So a one-off `--base-url` on pull **persists** as the vault's server for later commands. Whether that is intended ("Name the server this vault uses, once (it is recorded)", L935-L936) — appears so.
- unclear; whether the Type_Safe default for `Vault__Remote_Manager.storage` is guaranteed non-None when constructed bare (L924); the `except Exception` at L926-L927 would mask a failure as "no remote".
