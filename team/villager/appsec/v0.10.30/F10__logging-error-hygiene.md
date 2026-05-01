# F10 — Logging, Progress, and Debug-Log Hygiene

**Severity:** LOW
**Class:** Output stream / logging leak
**Disposition:** OK with two small docs/UX fixes
**Files:** `sgit_ai/cli/CLI__Progress.py`, `sgit_ai/cli/CLI__Debug_Log.py`,
`sgit_ai/sync/Vault__Inspector.py` (commit-chain printing)

## 1. Debug-Log Output (`--debug-log`)

`CLI__Debug_Log._print_entry` (line 35-50) writes to **stderr** the line:

```
    [METHOD] STATUS  DURATIONms  SENT_SIZE  RECV_SIZE  PATH  [ERR: ...]
```

`PATH` is the URL after `/api/` stripping and `unquote`. URLs are of shape:

- `vault/list/{vault_id}` — opaque hash
- `vault/destroy/{vault_id}` — opaque hash
- `vault/read/{vault_id}/{file_id}` — opaque hashes (file_id is `bare/data/{obj-cas-imm-...}` etc.)

**No plaintext path, filename, or content appears in the URL.** Verified
across `Vault__API.py` URL constructions. Debug log is safe.

`error[:60]` (line 49) is the response error string from the server. If a
malicious server crafted an error message containing client-supplied data
(e.g., echoed a path), that would appear in the debug log. **Server-side
discipline required**, but the worst case is the server reflecting data
the user already sent. Not a vulnerability against a benign server.

## 2. Progress Messages

`CLI__Progress` prints stage messages like:
- `▸ Cloning vault`
- `▸ Fetching blobs (50/100)`
- `▸ Encrypting and uploading (12/45)`

Reading the call sites in `Vault__Sync.py`, the messages contain:
- Stage names — fixed strings.
- Counts — integers.
- vault_id — opaque hash.
- token (in clone path, line 1852) — `vault://{token}` — the user's own
  share token, echoed back. This is on the user's local stdout; no leak to
  network.

I found **one concrete plaintext leak in progress output**:

```python
# Vault__Sync.py:1879 (clone_from_transfer)
_p('step', f"  Transfer found on SG/Send — downloading and importing...")
# Vault__Sync.py:1867
_p('step', f'  Derived transfer ID: {xfer_id}  (SHA-256("{token_str}")[:12])')
```

The second line **prints the user's plaintext token** in the SHA-256 echo.
This is on user stdout during their own clone — equivalent to echoing
their typed input. **Acceptable** but note: if the user pipes
`sgit clone --debug ... | tee log` they have just persisted their token to
disk. **One-line warning in the docs** is sufficient.

## 3. Commit Message Plaintext Echo

`Vault__Inspector` and `inspect_commit_chain` print commit metadata that is
plaintext **on the user's terminal** (the user has the read_key, decryption
is local). Specifically: messages like `add report.pdf`. The plaintext only
ever exists locally; on the wire and on the server it's encrypted in the
commit object.

**Concern:** if `--debug-log` is enabled at the same time as a `log` command
that prints commit messages, both stream to stderr/stdout. Different streams,
so they don't mix in the file system, but both visible in the same terminal.
**Document only**: do not enable `--debug-log` while reviewing sensitive
commit messages on a shared screen.

## 4. Error Path Hygiene

I scanned for f-strings in raise paths. Notable lines:
- `Vault__Sync.py:1810` — `probe only accepts simple tokens... '{token_str}'`.
  The token is echoed in the exception message (which the CLI displays).
  Token is the user's own input. **OK** but mid-char redaction would be a UX
  improvement. (See F04.)
- `Vault__Sync.py:1834-1837` — error contains `derived vault_id={vault_id}`.
  Hash, not plaintext. **OK.**
- `Vault__Sync.py:1876` — `f"No vault or transfer found for '{token_str}' "`.
  Echoes token. Same as above.
- `crypto/Vault__Crypto.py:50-54` — Invalid vault_id: prints the offending
  vault_id verbatim. The vault_id by definition is non-secret. **OK.**

**No plaintext file content** ever appears in an error path I found.
**No read_key, write_key, or passphrase** appears in any print/log/raise.
Verified by `grep -rn "read_key\b\|write_key\b" sgit_ai/cli/` and
`sgit_ai/sync/`: every match is either a function parameter or a key
derivation, never an output.

## 5. Test Coverage

- No tests assert "stderr is silent for sensitive operations".
- No tests grep stdout/stderr for `read_key`, `passphrase`, file contents.

**Recommended security tests:**
- `test_no_passphrase_in_progress(capsys)` — run a full commit, assert
  passphrase string never appears in `capsys.readouterr().out` or `.err`.
- `test_no_read_key_hex_in_debug_log(capsys)` — run with `--debug-log`,
  assert no 64-hex-char run appears.
- `test_no_filename_in_debug_log_url(capsys)` — assert URLs in debug log
  contain only opaque hashes.

## 6. Disposition

- **No code change required**.
- **Two doc additions:** scrollback caveat (also called out in F02 for rekey),
  `--debug-log` privacy note.
- **Three security tests** to add (capsys assertions).
