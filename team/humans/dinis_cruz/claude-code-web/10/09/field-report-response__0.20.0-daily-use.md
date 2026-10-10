# Response: "sgit-ai 0.20.0: issues found in daily use" (sgit.ai site session, 8–9 Oct)

**Date:** 2026-10-09 · **Branch:** `claude/charming-babbage-5hzcxq` → `dev` (ships in 0.21.0) ·
**Tests:** `tests/unit/review/test_Review__0_20_0__Field_Report.py` (32),
`tests/integration/test_Field_Report__0_20_0__Integration.py` (2, real SG/Send server)

All seven issues were still present on `dev`. Each is now fixed, and each test fails on the
old code. Both integration tests reproduce the report exactly on the real server: doctor gets
`401` and history log prints `(no commits)`.

| # | Issue | Root cause | Fix |
|---|---|---|---|
| 1 | clone hint says `sgit log` | stale text | Hint says `sgit history log`. Any top-level word that moved into a namespace prints its new place (`sgit: 'log' is now sgit history log`, exit 2). It is found from the parser, so the list never goes stale. **No alias:** CLAUDE.md rule 9 keeps `log` under `history`. |
| 2 | `history log` on a read-only clone: `(no commits)`, exit 0 | `resolve_read_key` only read `.sg_vault/local/vault_key`. A read-only clone has its read key in `clone_mode.json` instead. | Falls back to the clone's read key. A command that finds no key at all exits 1 and says what to pass. Also applies to `inspect tree` / `cat-object`. |
| 3 | `--vault-key <read key>:<id>` crashes `InvalidTag` | the read key was derived as if it were a passphrase | `--vault-key` follows clone's rules: a declared read key (`sgit_public_read_`, `sgit_private_read_`, with or without `:<id>`) or the bare `{64-hex}:{id}` shorthand. A key that doesn't open the vault gives "this key does not open this vault", exit 1. |
| 4 | doctor/status: "no remote configured" on the default server | doctor read only named remotes plus the `base_url` file; vaults made before 0.21.0 never recorded a server | doctor uses `resolve_remote`, which picks the same server push/pull use, and prints `No named remote; checking the server this vault uses: <url>`. status prints `Remote: <url> (not pushed yet …)`. New vaults already record their server from 0.21.0 (review S1). |
| 5 | doctor: `401 token rejected` with the token push uses | **doctor sent the token as `Authorization: Bearer` only.** SG/Send reads `x-sgraph-access-token`, and the stack middleware reads `X-API-Key`. `api_info` sent no token at all. | Every check sends the headers `Vault__API` sends, plus Bearer. |
| 6 | `pki encrypt --recipient <own fp>` needs own bundle imported | recipients were looked up in contacts only | New `PKI__Known_Keys`: looks in contacts, then in your own key pairs. `verify` and `decrypt` use it too. |
| 7 | `pki verify` prints the label only | — | `Signature valid (signer: <label>, <signing fp>, contact\|own key)`, plus `--json` → `{valid, signing_fingerprint, signer_label, signer_source}`. Exit 1 on invalid, also with `--json`. |

## Found while fixing (not in the report)

- **`pki decrypt` corrupted binary files.** Non-UTF-8 plaintext was decoded as latin-1, then
  written as UTF-8. `hybrid_decrypt` now also returns `plaintext_bytes`; decrypt writes those,
  mode 0600 through the secret writer.
- **`pki encrypt --fingerprint X` silently encrypted *unsigned*** when key X was not found. It
  now exits 1.
- **A wrong passphrase** in `sign` / `encrypt` / `decrypt` was a traceback. It is now
  `Error: wrong passphrase for key …`.
- **The doctor write probe could never pass on a real server.** It sent no write key. It now
  sends the clone's write key, and it skips on a read-only clone. Verified against SG/Send.
- On a read-only clone, doctor's `vault_known` now uses the clone's vault id; it used to skip.

## The two notes

- **Key from stdin:** `sgit clone - <dir>` reads the key from the first line of stdin. The same
  works for `clone-branch`, `clone-headless` and `clone-range`. Example:
  `pass show vault | sgit clone - demo`.
- **`pki decrypt --output PATH`**, and `--output -` for stdout. With stdout, messages go to
  stderr and no plaintext file is written. `pki encrypt --output` exists too.

## Not changed

- `sgit log` does not come back as an alias (rule 9). The moved-command message covers people
  and agents who learned the old name.
- A bare `--vault-key` whose passphrase is exactly 64 hex characters is read as the read-key
  shorthand. This is the same rule clone uses, and declaring it with
  `sgit_private_vault_` avoids it. With the wrong reading, the result is the clear "does not open
  this vault" error, never a wrong history.
