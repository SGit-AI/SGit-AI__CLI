## `resolve_remote` in sgit_ai/cli/CLI__Token_Store.py (L50-L106)

```python
# L64-L66 flags
base_url_flag = getattr(args, 'base_url', None); remote_flag = getattr(args, 'remote', None); verify_flag = getattr(args, 'verify_tls', None)
# L68-L71  --base-url wins; recorded via resolve_base_url; tls from flag/default
# L73-L87  --remote NAME: Vault__Remote_Manager().get_remote(directory, name); None → RuntimeError (re-raised, L84-L85); any other Exception swallowed (L86-L87)
# L89-L99  default remote: get_default(directory); Exception swallowed
# L101-L106 legacy: resolve_base_url(None, directory); if '' and .sg_vault exists → _unrecorded_server(); tls via resolve_tls_verify
```

**Purpose:** The precedence rule for which host a network command talks to (docstring L58-L62): `--base-url` > `--remote NAME` > default remote in `remotes.json` > legacy `base_url` file > the process default (`_unrecorded_server`). The server choice decides where the token, the write key header and the ciphertext go (TM-F15, TM-F22).

**Inputs & Assumptions:**
- `args`: argparse namespace; attributes read with `getattr(..., None)` so any command can call it.
- `directory` (str or None).
- Implicit: `remotes.json`, `base_url` file, `.sg_vault` existence, `SGIT_DEFAULT_BASE_URL` (via `_unrecorded_server`).
- Precondition that a non-existent `--remote NAME` is an error: established at L77-L79 and re-raised at L84-L85. But a `remotes.json` that fails to PARSE while `--remote` is given is swallowed (L86-L87) and the resolution silently continues to the default-remote branch (which also swallows, L98-L99) and then the legacy file / process default. **nothing found** that reports a corrupt `remotes.json`; the command proceeds against a server the user did not name.
- Precedence note: when `--base-url` is given, `resolve_base_url` at L70 RECORDS it (L25-L26), changing the legacy fallback for future commands.

**Outputs & Effects:**
- dict `{name, base_url, tls_verify}`; `name` is `'--base-url'`, the remote's name, or `''`.
- Side effects: `base_url` file write (L70 path); stderr warning from `_unrecorded_server` (L103).
- `tls_verify` for a named/default remote: the remote's recorded value unless the flag overrides (L80, L94).

**Block-by-Block:** four ordered branches, each returning. The `try/except Exception: pass` at L86-L87 and L98-L99 are the two places where configuration errors become silent fall-through.

**Cross-Function Dependencies:**
- Callees: `resolve_base_url`, `resolve_tls_verify`, `_unrecorded_server` (internal); `Vault__Remote_Manager.get_remote`/`get_default` (`Vault__Remote_Manager.py:L52-L65`; `_load_remotes` L111-L117 does `Schema__Remote_Config.from_json` on each entry — validation lives in that schema).
- Callers: `CLI__Vault.py:L816,L963,L1032,L1186,L1830,L1969,L2495`, `CLI__Diff.py:L25`, `CLI__Doctor.py:L170`.
- Invariant coupling: `CLI__Main.run` separately "pins the server per command" (TM-F22 row) — that logic is outside this slice and is what the Server_Pin security tests exercise (`test_Security__Fixed__Server_Pin.py::test_the_recorded_server_wins_for_every_command_including_bare_clients`).

**Open Questions:**
- unclear; need to inspect `CLI__Main.run` / `_pin_server` (not in slice) to see whether it runs BEFORE `resolve_remote` for every command and what it does when `remotes.json` is corrupt.
