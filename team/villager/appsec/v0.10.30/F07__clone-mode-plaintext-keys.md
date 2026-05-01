# F07 — `clone_mode.json` Plaintext Read-Key Persistence

**Severity:** MEDIUM
**Class:** Forensic-disk leak / accepted-risk-document-only
**Disposition:** ACCEPTED-RISK (per Dinis) — DOCUMENT explicitly
**Files:** `sgit_ai/sync/Vault__Sync.py:1485, 1550-1552, 1653-1656`,
`sgit_ai/sync/Vault__Storage.py:89-90`,
`sgit_ai/sync/Vault__Sync.py:2278-2290` (read path),
`tests/unit/sync/test_Vault__Storage__Clone_Mode.py`

## 1. The Persisted Format

```python
# Vault__Sync.py:1550, 1654
clone_mode = dict(mode='read-only', vault_id=vault_id, read_key=read_key_hex)
with open(storage.clone_mode_path(directory), 'w') as f:
    _json.dump(clone_mode, f, indent=2)
```

File location: `<vault_dir>/.sg_vault/local/clone_mode.json`. Contents:

```json
{
  "mode": "read-only",
  "vault_id": "abcd1234",
  "read_key": "<64 hex chars = 32-byte AES key>"
}
```

This is the **plaintext AES-256 read key** — sufficient to decrypt every
blob, every tree, every commit message, every filename in the vault. No
passphrase wrap, no OS keychain, no encryption-at-rest.

## 2. Threat-Model Position (per Dinis)

> "Intentional, like the other secrets we already store in `.sg_vault/local`."

Verified consistent: `local/vault_key` already stores `passphrase:vault_id`
plaintext for editable vaults. So clone_mode.json's read_key persistence is
the same trust boundary — anyone with read access to `.sg_vault/local/`
**holds the keys to the vault**. This is the documented threat model.

## 3. Comparable Files in `.sg_vault/local/`

| File | Plaintext content | Sensitivity |
|------|-------------------|-------------|
| `vault_key` | `passphrase:vault_id` (full edit credential) | HIGH |
| `clone_mode.json` (read-only clone) | `read_key_hex` (read-only credential) | HIGH (read) |
| `config.json` | `share_token`, `my_branch_id` | MEDIUM-HIGH |
| `remotes.json` | remote URLs + write_key | HIGH |
| `tracking.json` | branch tracking state | LOW |
| `push_state.json` | object IDs | LOW (see F09) |
| `private.pem` | branch signing private key | HIGH |

`clone_mode.json` storing a hex read_key is **consistent** with the rest
of the directory's trust model. **No inconsistency found.**

## 4. Forensic-Recovery Properties

If the user deletes the clone directory:
- `rm -rf <vault_dir>` → unlinks `clone_mode.json` but not its inode contents.
- The 64-hex string remains recoverable from disk for the OS-dependent
  retention window.
- An adversary who later acquires the disk image AND a snapshot of the
  encrypted server objects can decrypt the entire vault.

This is the **same** failure mode as the `vault_key` file. Already covered
by F02 recommendation: a `_secure_unlink` helper should apply to
`clone_mode.json` too.

## 5. File Permissions

The code uses plain `open(path, 'w')` with default umask. On Linux that
typically gives `0644` (world-readable). **Multi-user host risk:** any
local user can read another user's `clone_mode.json` and decrypt the vault.

**Recommendation (small fix):** apply `os.chmod(path, 0o600)` after writing
`clone_mode.json`, `vault_key`, `private.pem`, `config.json`, `remotes.json`.
The crypto envelope is fine; the OS-level ACL is the gap. **Document at
minimum, fix in a small PR ideally.**

## 6. Test Coverage

`tests/unit/sync/test_Vault__Storage__Clone_Mode.py` verifies:
- `clone_mode_path` returns the correct path.

But there are **no tests** that verify:
- The file mode is `0600`.
- The file content has the expected JSON shape.
- Removing `clone_mode.json` returns the clone to a non-readable state
  (i.e., proves load-bearing-ness — Mutation M6).

Mutation M6 (planned: write empty `read_key` field) — current tests for
read-only clone DO exercise the read path
(`test_Vault__Sync__Multi_Clone.py`), so this would likely fail there.
**Confirm with QA Phase 3 mutation run.**

## 7. Disposition

- **Accepted-risk-document-only** per Dinis. Add explicit note in user docs:
  "Anyone with filesystem access to `.sg_vault/local/` can decrypt your
  vault. Treat this directory like an SSH private key."
- **Small-fix recommended:** `os.chmod(path, 0o600)` for files in
  `.sg_vault/local/`. Group with F02 secure-unlink work.
- **Not a redesign trigger.**
