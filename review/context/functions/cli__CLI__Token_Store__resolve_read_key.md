## `resolve_read_key` in sgit_ai/cli/CLI__Token_Store.py (L205-L224)

```python
# L213-L224
raw = getattr(args, 'vault_key', None)
if raw:
    return self.read_key_from_credential(raw)
directory = getattr(args, 'directory', '.') or '.'
vault_key = self.load_vault_key(directory)
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto, READ_KEY_PREFIX
if vault_key:                                   # a vault key by definition: never the shorthand
    return Vault__Crypto().derive_keys_from_vault_key(vault_key)['read_key_bytes']
clone_mode = self.load_clone_mode(directory)
if clone_mode.get('mode') == 'read-only' and clone_mode.get('read_key'):
    return self.read_key_from_credential(READ_KEY_PREFIX + Vault__Crypto().strip_key_prefix(str(clone_mode['read_key'])))
return None
```

**Purpose:** The read key for local history/inspect commands (docstring L206-L212): `--vault-key` (any credential form) > the clone's `vault_key` file > a read-only clone's `clone_mode.json`. Caller: `CLI__Vault._read_key_or_exit` (L2221-L2232), which turns `None` into exit 1 and `ValueError` into an error line.

**Inputs & Assumptions:**
- `args.vault_key`: argv, any of vault key / declared read key / bare `{64-hex}:{id}` shorthand. Trust: untrusted; routed by `read_key_from_credential`.
- `args.directory`: defaults to `'.'`.
- Implicit: `vault_key` file, `clone_mode.json`.
- Precondition at L219: the `vault_key` FILE never holds the read-key shorthand. Established by the writers: every writer stores `format_vault_key(...)` of a key that passed `derive_keys_from_vault_key` (`Vault__Sync.py:L57,L123`, clone steps), and read-only clones write `clone_mode.json` instead and no `vault_key` (`Vault__Diff.py:L586-L588` docstring).
- At L223 the stored read key is re-declared as PRIVATE (`READ_KEY_PREFIX +`) before routing, so a `clone_mode.json` written from a public read key is still treated as a read key; `read_key_from_credential` then enforces 64 hex and raises `ValueError` otherwise — the only validation of `clone_mode['read_key']` on this path (since `load_clone_mode` skips the schema).

**Outputs & Effects:** `bytes` (32 for well-formed input), `None`, or `ValueError`. PBKDF2 runs on the vault-key paths. Pure.

**Cross-Function Dependencies:** `read_key_from_credential` (L226-L242), `load_vault_key` (L182-L191), `load_clone_mode` (L193-L203), `Vault__Crypto.derive_keys_from_vault_key`, `strip_key_prefix`. Tests: `test_CLI__Token_Store.py::test_resolve_read_key_*`, `tests/unit/cli/test_CLI__Commands.py::test_resolve_read_key_from_vault_file`.

**Open Questions:** none.
