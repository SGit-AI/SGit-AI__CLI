## `run` in sgit_ai/cli/CLI__Main.py (L822-L897)

**Purpose:** The process entry point after `main()`: parse argv, apply the moved-command and context gates, read a key from stdin when asked, **pin the server for the whole command**, set up debug logging, dispatch `args.func`, and map exceptions to exit codes and messages.

**Inputs & Assumptions:**
- `argv` (list | None): the command line. Trust: user input; may carry `--token`, `--base-url`, a vault key positional, `--read-key`, `--vault-key`, `--new-key`, `--key` (see `build_parser` record).
- Implicit: `os.getcwd()` for context detection (L847), `os.environ['SGIT_DEFAULT_BASE_URL']` (read and **written** by `_pin_vault_server`), `.sg_vault/local/{base_url,remotes.json,debug}` of the detected vault.

**Outputs & Effects:**
- `os.environ['SGIT_DEFAULT_BASE_URL']` set for the duration of `args.func` and restored in `finally` (L855, L894).
- Credential store opened for `vault` commands (L830-L833: `setup_credential_store`).
- stderr messages on error; exit codes 1/2/130.
- Everything else is the command's.

**Block-by-Block:**

```python
# L823-L824
parser = self.build_parser()
self._exit_if_moved_command(parser, sys.argv[1:] if argv is None else argv)
args   = parser.parse_args(argv)
```
- **What:** Parse. argparse puts a positional `vault_key` and `--token` into `args` as plain strings; they stay in `sys.argv` (visible in `ps`/history — the docs for `clone -` say so, L201-L204).

```python
# L844-L846
command = getattr(args, 'command', None) or ''
if command in self._KEY_FROM_STDIN and getattr(args, 'vault_key', None) == '-':
    args.vault_key = self._key_from_stdin()
```
- **What:** `sgit clone - <dir>` family: the key from stdin's first line (L1223-L1230), never in argv.
- **Assumes:** `_KEY_FROM_STDIN = ('clone', 'clone-branch', 'clone-headless', 'clone-range')` (L1221). Other key-taking commands (`init --vault-key`, `vault attach --vault-key`, `vault move --new-key`, `vault restore --key`, `vault derive-keys`) have no stdin form here; `vault add` uses `getpass` when `--vault-key` is omitted (`CLI__Vault.cmd_vault_add` L1660).

```python
# L847-L852
context = self._detect_context(args)
if (command in self._INSIDE_ONLY and context.is_outside() and not self._context_free_subcommand(args)): self._cmd_wrong_context(...)
if command in self._OUTSIDE_ONLY and context.is_inside(): self._cmd_wrong_context(...)
```
- **What:** inside/outside gates (`Vault__Context.detect_with_override(cwd, args.vault)`, L1268-L1272).

```python
# L854
pinned_env = self._pin_vault_server(args, command, context)
```
- **What:** Decide the server once (see record). After this line, every `Vault__API()` constructed anywhere in the process with no explicit `base_url` resolves to the vault's recorded server via `default_base_url()` (`Vault__API.py:L73-L76` → `setup()` L32-L35).
- **Depended on by:** every bare `Vault__API()` in `CLI__Vault` (`cmd_init` L330, `cmd_uninit` L410, `cmd_vault_ignore` L1617, `cmd_vault_attach` L1593, `_offer_clone_recovery` L89, `cmd_info` L1708, `_prompt_remote_setup` L1261, `cmd_vault_move` L633, L646…) and in core (`CLI__Main._partial_scope_of` L1005).

```python
# L856-L860
try: debug_log = self._setup_debug(args)
except Exception: debug_log = None
```
- **What:** `--debug` or `.sg_vault/local/debug == 'on'` enables `CLI__Debug_Log` on `self.vault.debug_log`, which `create_api` passes into every API (`CLI__Vault.create_api` L56-L60). The log prints method, status, timing, sizes and the **URL path** (`CLI__Debug_Log._print_entry` L35-L50, `_format_path` L52-L66) — file ids (object/ref/index ids), never headers, so no token. A presigned S3 URL logged by `_download_blobs_by_id`'s `debug_log.log_request('GET', s3_url)` (`Vault__Sync__Clone.py:L336`) prints the path portion of a **signed URL** (query string included after the first `/`), truncated to 70 chars (L64-L65) — the signature parameters are usually beyond that cut, but not by construction.

```python
# L862-L896
try: args.func(args)
except KeyboardInterrupt: ... exit 130
except RuntimeError as e: print(f'error: {e}', file=sys.stderr); exit 1
except Exception as e:
    ssl_hint = self._check_ssl_error(e) ...
    self._print_friendly_error(e, args)
    if debug_log: raise
    sys.exit(1)
finally:
    self._unpin_vault_server(pinned_env)
    if debug_log: debug_log.print_summary()
```
- **What:** Dispatch and error mapping. `RuntimeError` messages are printed verbatim — `Vault__API._api_error` builds those messages with token/key headers **masked** (`Vault__API.py:L477-L482`) and includes the request URL and the response body (L484-L490). The response body is server-controlled text printed to the terminal.
- With `--debug`, non-`RuntimeError` exceptions are **re-raised** after the friendly message (L886-L887): a full traceback, whose frames can carry locals — Python's default traceback does not print locals, so no key appears; a custom excepthook would.

**Cross-Function Dependencies:**
- Callees: `build_parser`, `_exit_if_moved_command`, `_key_from_stdin`, `_detect_context`, `_pin_vault_server`, `_unpin_vault_server`, `_setup_debug`, `_print_friendly_error`, `_check_ssl_error`.
- Callers: `sgit_ai/cli/__init__.py` `main()` (not read; CLAUDE.md rule 7).
- Shared state: `os.environ`.
- Tests: `tests/security/test_Security__Fixed__Server_Pin.py::*` drive `CLI__Main().run([...])` end to end.

**Open Questions:**
- unclear; `_print_friendly_error`'s generic branch (L1065-L1067) prints `str(error)` for any exception type — whether any code path raises an exception whose message embeds a key (e.g. a `ValueError` from `parse_vault_key` echoes the **vault_id** only, `Vault__Crypto.py:L131-L135`; `Safe_Str` validation errors echo the offending value — a malformed `--vault-key` would be echoed in full by a `Safe_Str__Vault_Key` constructor error). Not traced to a concrete raise site.
