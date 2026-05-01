# F02 — Rekey Key-Material Lifecycle

**Severity:** MEDIUM
**Class:** Forensic-disk residency / lifecycle hygiene
**Disposition:** REAL-FIX-NEEDED (small) + DOCUMENT
**Files:** `sgit_ai/sync/Vault__Sync.py:1759-1801`,
`sgit_ai/cli/CLI__Vault.py:989-1075`

## 1. Sequence Audited

```
rekey_wipe   → shutil.rmtree(.sg_vault/)
rekey_init   → init(directory, vault_key=new_vault_key, allow_nonempty=True)
rekey_commit → commit(directory, message='rekey')
```

## 2. Old `vault_key` File: Unlink, Not Wipe

`shutil.rmtree(sg_dir)` (line 1770) ultimately calls `os.unlink` on
`.sg_vault/local/vault_key`. **The file's plaintext bytes remain on disk**
(in unallocated blocks) until OS overwrite. On SSDs, TRIM may take seconds to
hours; on HDDs, it can persist for months.

- **Impact:** Forensic adversary with image-level disk access recovers the
  *old* `passphrase:vault_id`. Combined with the fact that the API does not
  guarantee server-side ciphertext destruction (delete-on-remote may only
  delete index, see F05), this means an attacker who recovers the old key AND
  has access to old server snapshots can decrypt the historical vault.
- **Mitigation strength needed:** Best-effort overwrite (`os.urandom` write
  before unlink) reduces forensic recovery window. NOT a hard guarantee on
  CoW filesystems (btrfs, APFS, ZFS).

**Recommendation:** Add a `_secure_unlink(path)` helper that opens the file,
overwrites with random bytes the same length, fsyncs, then unlinks. Apply to
`vault_key` and `private.pem` in `local/`. Document explicitly that on CoW
filesystems this is best-effort.

## 3. PBKDF2 LRU Retains Old Key Material

Cross-reference F03. After `rekey_wipe`, `_pbkdf2_cached` (module-level
`functools.lru_cache(maxsize=256)`, `Vault__Crypto.py:26`) still holds:

- `(old_passphrase_bytes, old_read_salt)` → old read_key
- `(old_passphrase_bytes, old_write_salt)` → old write_key

These survive in process memory until process exit OR until 256 distinct
keys evict them. For a CLI invocation that runs only `rekey`, the process
exits seconds later — fine. For a long-running agent (which the v0.10.30
"agent-friendly" CLI is intended to support), this is a residency
violation. See F03.

## 4. Window Where Old + New Coexist

`rekey_wipe` deletes the entire `.sg_vault/` then `rekey_init` creates
a new one. **There is no on-disk window** where both old and new vault_key
files exist — the rmtree completes before init runs. Verified by code
reading.

However: `rekey()` (line 1789) is **non-atomic** at the orchestration level.
If the process is killed between `rekey_wipe` (line 1796) and `rekey_init`
(line 1797), the working tree still exists but `.sg_vault/` is gone. The
vault is unbootable until the user runs `sgit init` or `sgit rekey init`
explicitly. **No data loss** (working files preserved), but recovery is
manual.

**Recommendation:** Document this in CLI help text. Optionally, add a sentinel
file `.sg_vault.rekey_in_progress` written atomically before wipe and removed
after commit; if found at next CLI invocation, prompt user to resume.

## 5. Server-side Ciphertext Survives Rekey

`rekey` does not call `delete_on_remote` itself. The CLI rekey wizard
explicitly asks the user (line 1024-1029):

> Have you run "sgit delete-on-remote" first?

This is correct UX — the user is warned. But the `rekey_wipe` operation
itself does not enforce that the remote was deleted. **Attacker with the old
key + old server snapshot can still decrypt the old vault**, regardless of
local rekey.

This is the **only correct behaviour** for a zero-knowledge system: the
server is not trusted to delete on command. But it must be made unmissable
in the docs and warning text.

## 6. New `vault_key` Printed on Stdout — INTENTIONAL

`CLI__Vault.cmd_rekey` line 1070 prints the new vault_key to stdout in a
banner:

```
SAVE YOUR NEW VAULT KEY — cannot be recovered:
    {init_r["vault_key"]}
```

**Per Dinis: intentional UX.** Residual risks to document:

- Shell history (`~/.bash_history`, `~/.zsh_history`) does NOT capture stdout
  — only commands. Safe.
- Terminal scrollback DOES capture it. User must `clear` or `reset` after.
- Tmux/screen pane buffers persist it.
- `sgit rekey 2>&1 | tee log` would write the key to a file. CLI cannot
  prevent user piping.
- CI captures it if rekey is ever run in CI (it shouldn't be).

**Recommendation:** Add a one-liner warning under the banner: *"Your terminal
scrollback now contains this key — clear it after copying."*

## 7. Test Coverage

`tests/unit/sync/test_Vault__Sync__Delete_Rekey.py:106-365` covers:
- New key returned ✓
- Vault_id changes ✓
- Working files preserved ✓
- Local vault_key file updated ✓
- Custom new key honoured ✓
- Empty vault, double-rekey, post-rekey commit/push ✓

**Gaps:**
- No test asserts the old `vault_key` file no longer contains old plaintext
  on disk after wipe. Mutation: replace `shutil.rmtree` with `pass` —
  `test_rekey_wipe_removes_objects` would catch via `os.path.isdir(sg_dir)`
  check (line 195). Confirmed mutation-detected.
- No test covers the "kill between wipe and init" recovery path.
- No test asserts the LRU cache is small / cleared after rekey.
- No test asserts the new `vault_key` file is created with `0600` permissions
  (forensic-hygiene gap).

## 8. Severity & Disposition

- **Real fix:** secure-unlink helper for `vault_key`, `private.pem`. Small
  PR, well-defined.
- **Doc fix:** CoW-filesystem caveat, scrollback caveat, kill-between-wipe-init
  recovery procedure.
- **No redesign needed.** Crypto envelope is fine.
