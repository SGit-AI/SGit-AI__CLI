## `cmd_clone` in sgit_ai/cli/CLI__Vault.py (L208-L326)

**Purpose:** `sgit clone <key> [dir]`: resolve credentials and server, choose full vs read-only clone, run it, persist token and server for the new clone, print a summary that **includes the read key** for a full clone.

**Inputs & Assumptions:**
- `args.vault_key` (argv or stdin via `run`), `args.read_key`, `args.token`, `args.base_url`, `args.verify_tls`, `args.transport`, `args.force`, `args.sparse`, `args.depth`, `args.scope_paths`.
- `clone` is in `_CREATES_VAULT`: no server pin; `create_sync(base_url, token, …)` → `create_api` → `Vault__API__Auto(base_url or '')` → `setup()` → `default_base_url()` honours `SGIT_DEFAULT_BASE_URL` when no `--base-url`.

**Outputs & Effects:**
- `token = resolve_token(args.token, None)` (L210) — not saved yet (no directory); saved after the clone to the **new** directory (L253, L302-L303: `save_token` → `write_private`, 0600).
- Server recorded in the new clone: RO clone `base_url or sync.api.base_url` (L254); full clone `sync.api.base_url` (L297, L304-L305) — so the clone always records the server it actually used (which may be the env-var default).
- `--force` ⇒ `shutil.rmtree(directory)` (L229-L231) before cloning — deletes whatever is at `directory`, vault or not (user-chosen path).
- stdout: `(detected 64-hex read key …)` when the shorthand fired (L225); `_warn_private_key_over_plain_http` (L226, stderr; private key + `http://`); after a full clone: **`Read key:  sgit_private_read_<hex>  (share for read-only access)`** (L321-L322, derived by PBKDF2 at L289-L294). The vault key itself is not echoed. The read key is printed on every full clone, not on request.
- A `RuntimeError` containing `Directory is not empty` triggers `_offer_clone_recovery` (L292-L295).

**Block-by-Block:**

```python
# L219-L226
vault_key, read_key, detected = self._resolve_clone_credential(args.vault_key, getattr(args, 'read_key', None))
...
self._warn_private_key_over_plain_http(args.vault_key, base_url)
```
- See `_resolve_clone_credential` record. The warning is keyed on `base_url` (the flag) only — an `http://` default from the environment variable is **not** warned about (L150-L151 checks the passed `base_url`, which is `None` when the env var supplies the server).

```python
# L239-L254 (read-only)
result = sync.clone_read_only(vault_id_arg, read_key, directory, ...)
if token: self.token_store.save_token(token, result['directory'])
self.token_store.save_base_url(base_url or str(sync.api.base_url or ''), result['directory'])
```

```python
# L297-L305 (full)
effective_base_url = str(sync.api.base_url) if sync.api.base_url else ''
keys = Vault__Crypto().derive_keys_from_vault_key(vault_key.removeprefix('vault://'))   # for the read-key print
if token: save_token(...)
if effective_base_url: save_base_url(...)
```

**Cross-Function Dependencies:**
- Callees: `CLI__Token_Store.resolve_token`/`resolve_tls_verify`/`save_token`/`save_base_url`; `create_sync`; `_resolve_clone_credential`; `_warn_private_key_over_plain_http`; `Vault__Sync.clone`/`clone_read_only`; `_offer_clone_recovery`; `Vault__Crypto.derive_keys_from_vault_key`/`format_read_key`; `describe_transport`.
- Callers: `clone` parser L198-L218.
- Tests: `tests/unit/cli/test_CLI__Clone_Family.py`, `tests/unit/cli/test_CLI__Vault__Commands.py` (clone section).

**Open Questions:**
- unclear; printing the read key after every full clone (L321-L322) is a deliberate feature ("share for read-only access"); it means a CI log of `sgit clone` contains a credential that reads the whole vault forever (A3). Whether a flag to suppress it exists — none found in `build_parser`.
- unclear; `_warn_private_key_over_plain_http` not firing for an env-var-supplied `http://` default (TM-R10 accepts plain http).
