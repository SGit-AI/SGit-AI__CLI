# Finding 02 — New commands: CLI boundary respected, dispatch is thin

**Verdict:** `BOUNDARY OK` for `probe`, `delete-on-remote`, `rekey`, `write`,
`ls`, `fetch`, `cat` (sparse extensions).
**One observation:** `cmd_rekey` is a 90-line *interactive wizard* — that's a
lot of presentation logic in `CLI__Vault.py`, but it stays in CLI and never
reaches into sync internals, so the boundary is respected.

---

## 1. Where does the logic live?

| Command | CLI handler (CLI__Vault.py) | Domain method (Vault__Sync.py) | Verdict |
|---|---|---|---|
| `probe` | `cmd_probe` (lines 928–954) | `probe_token` (1803–1837) | thin dispatch |
| `delete-on-remote` | `cmd_delete_on_remote` (956–985) | `delete_on_remote` (1724–1734) | thin dispatch + UX |
| `rekey` | `cmd_rekey` (989–1074) | `rekey` (1789–1801) calls `rekey_wipe`/`rekey_init`/`rekey_commit` | thin dispatch + wizard UX |
| `rekey check/wipe/init/commit` | `cmd_rekey_check`/`_wipe`/`_init`/`_commit` (1076–1149) | `rekey_check`/`rekey_wipe`/`rekey_init`/`rekey_commit` (1736–1787) | thin dispatch |
| `write` | `cmd_write` (1328–1381) | `write_file` (227–335) | thin dispatch |
| `ls` | `cmd_ls` (1232–1265) | `sparse_ls` (2075–2096) | thin dispatch |
| `fetch` | `cmd_fetch` (1267–1293) | `sparse_fetch` (2098–2175) | thin dispatch |
| `cat` | `cmd_cat` (1295–1326) | `sparse_cat` / `sparse_ls` (2177+ / 2075) | thin dispatch |

Each handler does: parse args → resolve token/base_url → call `Vault__Sync` →
print/format output. **No business logic leaks into CLI.**

`cli/__init__.py` is 7 lines — imports + `main()` delegate to `CLI__Main().run()`.
**Rule 7 (no logic in `cli/__init__.py`) — UPHELD.**

## 2. Notable observations (not violations)

### 2a. `cmd_rekey` is large but OK

90 lines for `cmd_rekey` is on the high end for a CLI handler, but every
non-`print` line is either argument plumbing, an interactive prompt, or a
delegation back to `sync.rekey_*`. No vault state is mutated by the CLI
handler directly. The presentation logic is tightly coupled to UX (the wizard
banner, the YES/N prompts), which is appropriate for CLI.

If we wanted to keep `CLI__Vault` slim, the wizard could move into a
`CLI__Rekey_Wizard` class, but that's a polish refactor, not a boundary fix.
**Out of scope** per Villager rules.

### 2b. `cmd_write` instantiates `Vault__Sync` directly (line 1358)

```python
sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
```

Other commands use `self.create_sync(base_url, token)`. `cmd_write` skips that
helper for the *initial* write (no remote needed) but then calls
`self.create_sync(...)` for the optional `--push` step. The two `Vault__Sync`
instances share no state. Functionally fine — the API client is stateless —
but inconsistent with the rest of the file. Flag for Dev as a small
consistency cleanup; not a boundary issue.

### 2c. `delete_on_remote`'s read-only guard lives in BOTH layers

`cmd_delete_on_remote` checks `c.write_key` before prompting (line 964). The
domain method `delete_on_remote` *also* checks `c.write_key` (line 1732). This
is appropriate defence-in-depth — a programmatic caller bypassing the CLI
still hits the guard — but worth noting that the test only covers the domain
guard via clone_mode.json fixture (`test_delete_on_remote_read_only_raises`).

### 2d. `rekey` wizard reaches into `_init_components` indirectly via `rekey_check`

`rekey_check` calls `_init_components`, which means the wizard's "Current
vault" preamble works on read-only clones too. But `rekey_wipe` blows the
`.sg_vault/` directory regardless of read-only state. **No read-only guard on
`rekey_wipe` or `rekey`.** Test coverage doesn't exercise this. See
finding 04 for the duplication implications and finding 06 for the read-only
question more broadly.

This is an architectural question, not a boundary one — should `rekey` be
allowed on a read-only clone? My read of the design intent: rekey is
"rebuild the vault from working files under a new key", and a read-only clone
has no write-key to push the result, so rekey would produce an unpushable
local state. Probably should refuse, mirroring `delete_on_remote`. Flag for
Architect+Dev review.

## 3. Naming conventions on new methods

All new domain methods on `Vault__Sync`:
- `probe_token`, `delete_on_remote`, `rekey`, `rekey_check`, `rekey_wipe`,
  `rekey_init`, `rekey_commit`, `write_file`, `sparse_ls`, `sparse_fetch`,
  `sparse_cat`, `_clone_download_blobs`, `_fetch_missing_objects`.

All snake_case, all on `Vault__Sync` (a `Type_Safe` class). No module-level
helpers introduced. **Convention upheld.**

`Vault__Storage` got two new methods, both following the existing pattern:
- `find_vault_root(directory)` — `@classmethod`, walks up looking for `.sg_vault/`.
- `push_state_path(directory)`, `clone_mode_path(directory)`.

Note the `@classmethod` on `find_vault_root`. Project rule 2 says "no
`@staticmethod`" but is silent on `@classmethod`. This is a pragmatic choice
because the method doesn't need an instance. Not a violation, but a future
Architect/Sherpa might want to clarify the rule.

## 4. Hand-off

- **Dev:** consider unifying the `Vault__Sync` instantiation pattern in
  `cmd_write`. Cosmetic.
- **Sherpa/Architect (joint):** decide whether `rekey` should refuse on
  read-only clones. Add to acceptance criteria for next sprint.
- **AppSec:** the read-only guard pattern is now duplicated across CLI and
  domain layers — confirm both are tested and that bypass paths (raw
  `Vault__Sync` use) are covered.
