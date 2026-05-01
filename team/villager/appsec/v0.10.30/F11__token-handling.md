# F11 — Token Handling: Probe / Delete / Rekey / Token-Store

**Severity:** LOW (residual)
**Class:** Token persistence + UX
**Disposition:** ACCEPTED-RISK (per Dinis); two minor fixes recommended
**Files:** `sgit_ai/cli/CLI__Token_Store.py`,
`sgit_ai/cli/CLI__Vault.py:cmd_rekey`,
`sgit_ai/transfer/Simple_Token.py`

## 1. Persistence Surfaces

| File | Stored | Risk |
|------|--------|------|
| `.sg_vault/local/vault_key` | Full edit credential `passphrase:vault_id` | HIGH |
| `.sg_vault/local/clone_mode.json` | `read_key_hex` (read-only) | HIGH (see F07) |
| `.sg_vault/local/token` | Server bearer token (CLI__Token_Store) | HIGH |
| `.sg_vault/local/config.json` | `share_token`, `my_branch_id` | MEDIUM |
| `.sg_vault/local/remotes.json` | remote URLs + write_key | HIGH |
| `.sg_vault/local/base_url` | server URL | LOW |
| process-stdout (rekey) | New `vault_key` printed to terminal | DOCUMENTED |
| process-stdout (probe) | Echoed input token | LOW |

All files use plain `open(...)` with default umask. **Recommend chmod 0600**
on every save; bundle with F02/F07 fixes.

## 2. Tokens NOT Persisted Outside `vault_key`

I grep'd for `os.environ`, `os.putenv`, `subprocess.run`, and
`commands.getoutput`. No code path writes a token to:
- Environment variables.
- `argv` of a subprocess.
- Any file outside `.sg_vault/local/`.

**Verified clean.** Tokens stay in-process or in `.sg_vault/local/`.

## 3. Rekey: New Vault-Key Printed (per Dinis: intentional)

`CLI__Vault.cmd_rekey:1064-1075`:

```
SAVE YOUR NEW VAULT KEY — cannot be recovered:

    {init_r["vault_key"]}
```

**Accepted as intentional UX.** Residual considerations (already in F02):
- Terminal scrollback retains it.
- `tee log` redirects persist it.
- Tmux/screen history persists it.

**Recommended addition to the printed banner (one line):**

> *"Your terminal scrollback now contains this key. Copy it to a password
> manager and clear scrollback (`clear` / Cmd+K) before continuing."*

Trivial UX change, AppSec-meaningful.

## 4. Partial Token Masking

I checked all f-string token echoes:

| Location | Echoed Form | Comment |
|----------|-------------|---------|
| `cmd_probe:943,950` | full token | OK (user input echo) |
| `cmd_rekey:1070` | full new vault_key | intentional |
| Vault__Sync.py:1852 | `vault://{token}` in progress | local stdout only |
| Vault__Sync.py:1834-1837 | full token in error | echoes user input |
| Vault__Sync.py:1876 | full token in error | echoes user input |

**No location echoes a token the user did not just type.** Specifically: the
read_key_hex in `clone_mode.json` is **never printed** to stdout/stderr.
Verified by `grep -rn "read_key_hex\|read_key" sgit_ai/cli/`.

## 5. CLI__Token_Store Audit

`save_token` opens with default mode and writes the token. No chmod.
`load_token` reads from `local/token` then a legacy fallback at `.sg_vault/token`.
**Two locations** that could hold a stale token. Recommendation: deprecate
the legacy location and migrate on read.

## 6. Test Coverage

Tests for token store cover save/load/round-trip (probably; check
`tests/unit/cli/`). No tests assert:
- Token files are created with mode 0600.
- Tokens never appear in stdout during commit/push/pull.
- The rekey banner does NOT print the **old** vault_key (regression risk:
  a future refactor that prints `info["vault_id"]` could accidentally
  include passphrase if `vault_id[:8]...` slicing changes).

**Look at line 1032:** `print(f'  Key starts with: {info["vault_id"][:8]}...')`.
This is the **vault_id** (the part after the colon, non-secret), not the
passphrase. **Confirmed safe** by reading `rekey_check` (line 1736-1757):
the dict has `vault_id` only, never `vault_key`. So this line is fine. **But
a one-liner test would prevent regression:**

```python
def test_rekey_does_not_print_passphrase(env, sync, capsys):
    pass_string = env.vault_key.split(':')[0]
    sync.rekey_check(env.vault_dir)  # purely informational
    out = capsys.readouterr().out
    assert pass_string not in out
```

## 7. Disposition

- **Accepted-risk-document-only** for the rekey stdout print.
- **Small-fix recommended:**
  - Add `os.chmod(path, 0o600)` to all token/key file writes.
  - Add scrollback warning to rekey banner.
  - Deprecate legacy token location.
- **Three regression tests** (no-passphrase-leak, no-old-key-leak,
  file-mode-0600).
