# Brief — `sgit vault backup` and `sgit vault restore`

**Date:** 2026-05-06
**Audience:** Sonnet executor + Sonnet reviewer (two-session pattern)
**Scheduling:** ships in the same sprint as `00h` (`vault move`) and `00i` (move tests). Implement BEFORE move tests so the testing scenarios can use `vault backup` for setup. Estimated effort: ~1 day combined (backup ~3h, restore ~5h, tests ~2h).
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Two reasons:

1. **Symmetry with `vault move`.** `vault move` already produces a backup zip as part of its destructive boundary (step 7 of the move workflow). Exposing that primitive as a standalone command gives users the natural "save state before doing something risky" tool. Particularly useful for testing the `vault move` flow itself — back up first, try the move, restore if something looks off.

2. **Disaster recovery primitive.** A vault is data the user cares about. The ability to take a snapshot, store it offline (USB drive, S3, encrypted external disk), and restore it later — independent of the SG/Send server — is a property the system should have on day one.

Backup and restore are the two halves of the same operation. They share the zip format, the sha256 integrity check, and the `--include-key` opt-in. Build them together.

---

## 2. `sgit vault backup`

```
sgit vault backup [<directory>]
    [--output-dir <dir>]           # default: <directory>/.sg_vault/backups/
    [--label <text>]               # human-readable suffix in the filename
    [--include-key]                # default off — opt-in to embed VAULT-KEY in the zip
    [--yes]                        # skip the include-key confirmation prompt
```

### 2a. Behaviour

1. Validate `<directory>` is a vault (`.sg_vault/` exists; `local/config.json` parses).
2. Refuse if there are uncommitted changes (`sgit status` would show modifications). The backup represents committed state; warn-and-abort if dirty unless `--allow-dirty` is passed (defer this flag to a follow-up).
3. Compute target path: `<output-dir>/<vault-id>__<ts>__<label>.zip`. Label defaults to `manual`. Timestamp format: `YYYY-MM-DDTHH-MM-SSZ` (filesystem-safe).
4. Build the zip, in order:
   - `bare/data/` (all object files, ZIP_STORED — no compression because encrypted bytes are high-entropy)
   - `bare/refs/`
   - `bare/indexes/`
   - `local/config.json`
   - `local/move-history.json` (if present)
   - `local/migrations.json` (if present)
   - `VAULT-KEY` — **only if `--include-key` was passed AND user confirmed the prompt**
5. Compute SHA-256 of the zip; write `<target>.sha256` sidecar.
6. Print the result to stdout:
   ```
   Backup written:
     /path/to/output/<vault-id>__<ts>__<label>.zip
     sha256: <hash>
     size:   <bytes>
     vault-key included: yes/no
   ```

### 2b. Include-key prompt UX

When `--include-key` is passed (and `--yes` is NOT), show:

```
  Including the vault-key inside the backup zip means anyone who
  reads the zip can decrypt all your data.

  This is convenient (the zip is self-sufficient for restore) but
  defeats the purpose of encryption-at-rest if the zip leaks.

  Default behaviour stores the encrypted bytes only — restore requires
  the vault-key separately.

  Include vault-key in the backup? [y/N] →
```

Default is N. Even with `--include-key` flag, the prompt asks for explicit confirmation unless `--yes` is also passed.

### 2c. Workflow integration

Register `Workflow__Vault_Backup` (single step is fine — `Step__Backup__Build_Zip`) so it appears in `sgit dev workflow list` and gets trace-log support. The implementation lives in `sgit_ai/core/actions/backup/Vault__Backup.py` per `00h §5d`.

---

## 3. `sgit vault restore`

```
sgit vault restore <source> <destination>
    [--mode bare|expanded]         # default: expanded
    [--key <vault-key>]            # required for expanded mode if zip doesn't include the key
    [--yes]                        # skip confirmation prompts
```

### 3a. Source forms

The `<source>` argument accepts:

- **Path to a backup zip:** `/path/to/vault__ts__label.zip` (absolute or relative)
- **Vault + backup-id reference:** `<vault-dir>:<backup-id>` — e.g. `./my-vault:ww7f3a-pasture-2841__2026-05-06T18-00-00Z`. Looks inside `<vault-dir>/.sg_vault/backups/` for the matching zip. The shorter form is just the timestamp prefix; sgit resolves to a unique match or errors if ambiguous.

### 3b. Destination validation

The `<destination>` must satisfy:

1. **Doesn't currently exist** (or exists but is empty). If it exists with any files in it, error with `"destination is not empty"`.
2. **Has no vault in any parent path.** Walk up from `<destination>` looking for `.sg_vault/`. If found at any level, error: `"cannot restore inside an existing vault: <path>"`. This prevents accidental nesting.
3. **Is writable** (sanity check: try `mkdir -p` then remove if didn't pre-exist).

The "no vault in parents" rule is non-negotiable. Test it explicitly.

### 3c. Mode: `bare`

Extract the encrypted `.sg_vault/` directory only:
- `bare/data/`, `bare/refs/`, `bare/indexes/`, `local/config.json`, `local/move-history.json`, `local/migrations.json`
- **Does not extract VAULT-KEY** even if it's in the zip (the user can opt to copy it in manually if they want).
- **Does not check out a working copy.**
- Result: a vault directory that's identical to a clone-headless or clone-bare clone. The user can `cd` in and run `sgit history log`, but no working files exist.

This mode never requires the vault-key. Useful for archival inspection or for setting up a vault that will be re-keyed via `vault move` before any working-copy extraction.

### 3d. Mode: `expanded`

Same as bare, plus:
- Reads the vault-key from `--key` flag, OR from the zip if it was included, OR from a prompt asking the user to paste it.
- Walks the HEAD tree of every active named branch and checks out files into `<destination>/`.
- Result: a fully usable vault — `<destination>/.sg_vault/` plus the working copy at the root.

If neither the zip nor `--key` provides a vault-key, prompt:
```
  This zip does not include the vault-key (encrypted-only backup).
  Restore mode is 'expanded' — the working copy cannot be extracted
  without the key.

  Options:
    1. Re-run with --mode bare    (skip working-copy extraction)
    2. Re-run with --key <key>    (provide the key inline)
    3. Paste the vault-key now:    →
```

### 3e. Workflow integration

`Workflow__Vault_Restore` with steps:
1. `Step__Restore__Validate_Destination` — empty + no parent vault.
2. `Step__Restore__Verify_Zip_Integrity` — sha256 match against sidecar.
3. `Step__Restore__Extract_Bare` — write `bare/`, `refs/`, `indexes/`, `local/`.
4. `Step__Restore__Resolve_Vault_Key` — only if mode=expanded; reads from zip / flag / prompt.
5. `Step__Restore__Extract_Working_Copy` — only if mode=expanded; reuses the existing `Step__Clone__Extract_Working_Copy` logic.

Failure at any step before 3 leaves nothing on disk. Failure at 3+ leaves a partially-extracted destination — the recovery is `rm -rf <destination>` and retry.

### 3f. Behaviour after restore

The restored vault is **fully self-contained but offline**. It points at whatever API URL was in `local/config.json` at the time of the backup.

- `sgit status` works.
- `sgit history log` works.
- `sgit pull` will hit the original server. If the original vault still exists there, pull may show divergence (the backup is a snapshot from earlier). If the original vault was deleted (e.g. after a `vault move`), pull will fail with "vault not found" — the user can then `sgit vault move --to <new-server>` to relocate, or simply work locally.
- `sgit commit` works — produces local commits.
- `sgit push` will succeed only if the original server still has the vault and the local clone is fast-forward-able. Otherwise the user must move the vault to a new identity first.

The brief should document this behaviour clearly — the restored vault has the same vault-id as when it was backed up; what happens on the server is independent.

### 3g. Listing available backups

For convenience, expose:
```
sgit vault backups [<directory>]
```
Lists all backups in `<directory>/.sg_vault/backups/` with timestamp, label, size, vault-key-included flag, sha256 prefix. Useful for the user to find the backup they want to restore.

```
$ sgit vault backups
Backups in /path/to/vault/.sg_vault/backups/:

  ww7f3a-pasture-2841__2026-05-06T18-00-00Z__manual.zip       3.2 MB   key:no    sha256: a1b2c3d4...
  ww7f3a-pasture-2841__2026-05-06T18-30-00Z__before-move.zip  3.2 MB   key:no    sha256: e5f6a7b8...
  ww7f3a-pasture-2841__2026-05-06T19-15-00Z__after-experiment.zip  3.4 MB  key:yes  sha256: c9d0e1f2...
```

---

## 4. Implementation

### 4a. Files

```
sgit_ai/core/actions/backup/
├── __init__.py
├── Vault__Backup.py            # backup class (also called by Workflow__Vault_Move step 7)
└── Vault__Restore.py           # restore class

sgit_ai/workflow/backup/
├── __init__.py
├── Workflow__Vault_Backup.py
├── Workflow__Vault_Restore.py
├── Backup__Workspace.py
├── Restore__Workspace.py
└── steps/
    ├── Step__Backup__Build_Zip.py
    ├── Step__Restore__Validate_Destination.py
    ├── Step__Restore__Verify_Zip_Integrity.py
    ├── Step__Restore__Extract_Bare.py
    ├── Step__Restore__Resolve_Vault_Key.py
    └── Step__Restore__Extract_Working_Copy.py

sgit_ai/schemas/backup/
├── __init__.py
└── Schema__Backup_Manifest.py    # metadata file inside the zip
```

### 4b. Manifest inside the zip

A small `manifest.json` at the zip root carries metadata about the backup so restore can validate compatibility:

```json
{
  "schema_version": 1,
  "vault_id":       "ww7f3a-pasture-2841",
  "key_generation": 2,
  "created_at":     "2026-05-06T18:00:00Z",
  "created_by":     "sgit v0.14.0",
  "label":          "manual",
  "includes_key":   false,
  "object_count":   500,
  "byte_size":      3284123
}
```

`Schema__Backup_Manifest` round-trips through Type_Safe. On restore, schema_version is validated; mismatched versions error clearly.

### 4c. CLI handlers

In `sgit_ai/cli/CLI__Vault.py`:
- `cmd_backup` — wraps `Workflow__Vault_Backup`.
- `cmd_restore` — wraps `Workflow__Vault_Restore`.
- `cmd_backups` (list) — reads the backups dir, parses manifests, prints the table.

In `sgit_ai/cli/CLI__Main.py`:
- Register all three under the `vault` namespace inside `_register_vault_ns`.

---

## 5. Tests

In `tests/unit/core/actions/backup/`:

### 5a. `test_Vault__Backup.py`

1. `test_backup_creates_zip_at_default_path` — backup a vault, assert zip exists at `.sg_vault/backups/<vault-id>__<ts>__manual.zip`.
2. `test_backup_zip_contents_match_vault` — unzip, assert byte-equality of `bare/`, `refs/`, `indexes/`, `local/config.json` against the source.
3. `test_backup_excludes_vault_key_by_default` — assert no `VAULT-KEY` in the zip.
4. `test_backup_includes_key_when_opted_in` — `--include-key --yes`; assert key present.
5. `test_backup_sha256_sidecar_matches_zip` — read sidecar, hash zip, assert equal.
6. `test_backup_with_label` — `--label "before-move"`; assert filename contains `__before-move.zip`.
7. `test_backup_to_external_dir` — `--output-dir /tmp/my-backups/`; assert zip lands there, default backups/ dir not created.
8. `test_backup_refuses_dirty_working_copy` — modify a file post-commit; backup errors with "uncommitted changes".
9. `test_backup_manifest_present_and_typed` — extract manifest.json; round-trip via `Schema__Backup_Manifest`.
10. `test_two_backups_coexist` — back up twice; assert both zips present, neither overwrote.

### 5b. `test_Vault__Restore.py`

1. `test_restore_bare_creates_offline_vault` — backup, restore to fresh dir in bare mode, assert `.sg_vault/` extracted, no working copy at root.
2. `test_restore_expanded_with_key_flag` — `--key <key> --mode expanded`; assert working copy extracted, files match HEAD tree.
3. `test_restore_expanded_with_key_in_zip` — backup with `--include-key`; restore expanded without `--key` flag; assert success.
4. `test_restore_expanded_without_key_errors` — backup without key; restore expanded without `--key`; assert prompt-or-error path triggers.
5. `test_restore_validates_zip_sha256` — corrupt the zip after backup; restore fails with "integrity check failed".
6. `test_restore_rejects_existing_destination` — destination dir contains files; restore errors.
7. `test_restore_rejects_nested_in_existing_vault` — destination is inside another vault directory tree; restore errors with "cannot restore inside an existing vault".
8. `test_restore_via_vault_dir_colon_backup_id` — source form `./my-vault:<ts-prefix>`; assert resolution works.
9. `test_restore_via_vault_dir_ambiguous_match` — multiple backups match the prefix; restore errors with "ambiguous backup id" listing the candidates.
10. `test_restore_preserves_vault_id` — backup vault Vid0; restore; assert the restored vault's vault-id is still Vid0.
11. `test_restore_preserves_move_history` — vault that's been moved; backup; restore; assert move-history.json restored intact.
12. `test_restore_history_log_walks_all_commits` — restored vault's `sgit history log` shows the same commits as the source.

### 5c. `test_CLI__Vault__Backup__Prompts.py` and `test_CLI__Vault__Restore__Prompts.py`

- `--include-key` without `--yes` triggers the prompt; user can decline (key not included) or accept.
- Restore expanded without key triggers the resolve prompt; pasted key is accepted; option 1 (downgrade to bare) and option 2 (re-run with flag) both produce sensible errors/behaviour.

### 5d. Integration with the move test suite (`00i`)

Update `tests/qa/sync/test_Vault__Move__Multi_Round.py` to use `sgit vault backup` as the explicit setup step before each move. Verify each backup zip restores cleanly post-test:
- After MOVE 1, restore B1 to a fresh dir with the OLD key — assert it produces V0 state.
- After MOVE 3, restore B1 → V0, B2 → V1, B3 → V2 — independent restorations.

This integration tightens the move tests too: backup is the canonical "checkpoint" mechanism, and restore is the canonical "I want to verify the backup actually captured everything" mechanism. Both are needed for the move tests to be properly water-tight.

---

## 6. Why this lands in this sprint

- **Backup/restore is small** — most of the work is the zip handling and the workflow scaffolding, both well-trodden in the codebase.
- **It strengthens `vault move` testing** — the move tests gain a meaningful checkpoint primitive. Without `vault backup`, the move tests have to construct their own setup snapshots ad-hoc.
- **It's a load-bearing user safety feature** — if we ship `vault move` (a destructive operation) without `vault backup` (its safety net), the UX is asymmetric. Users will reasonably expect "before I move, let me back up." That intuition should map to a real command.
- **The shared infrastructure with `vault move`** — the zip format, sha256 sidecar, manifest schema, `Vault__Backup` class — is already partly designed in `00h §5d`. Promoting it to a standalone command costs little extra.

The implementation order should be:
1. `Vault__Backup` (used by `00h` step 7 AND the standalone `cmd_backup`).
2. `Schema__Backup_Manifest`.
3. Standalone `cmd_backup` + `cmd_backups` (list).
4. `Vault__Restore` + workflow steps.
5. `cmd_restore` and prompts.
6. Tests (5a, 5b, 5c).
7. Update `00i` move tests to use the new commands.

---

## 7. Out of scope for this brief

- **Incremental backups** — every backup is a full zip. If two consecutive backups of a 500-MB vault waste 500 MB, that's the user's problem (they can delete old ones; or use a future incremental flag). Don't optimise prematurely.
- **Encrypted backups at the zip layer** — the contents are already encrypted at the object-store level. Adding ZIP encryption (e.g. AES-encrypted zip) is double-belt; not needed for v1. The `--include-key` opt-in handles the only realistic concern.
- **Cloud upload of backups** — `--output-dir s3://my-bucket/backups/` would be nice but is a separate brief. For now, users can `aws s3 cp` the local zip themselves.
- **Auto-backup on schedule** — cron-style hooks for nightly backups. Defer.
- **Cross-vault restore** — restoring backup A into vault B's working tree. Not useful; not supported.
- **Backup pruning** — `sgit vault backups --prune-older-than 30d`. Defer to a follow-up brief once usage patterns emerge.

---

## 8. Verification checklist

When done:

- `sgit vault backup .` writes a zip in `.sg_vault/backups/`.
- `sgit vault backup . --include-key --yes` writes a zip that contains VAULT-KEY.
- `sgit vault backups` lists the backups with metadata.
- `sgit vault restore <zip> <dest> --mode bare` produces an offline-readable `.sg_vault/`.
- `sgit vault restore <zip> <dest> --mode expanded --key <k>` produces a fully working vault.
- `sgit vault restore <zip> <dest>` errors when `<dest>` is inside an existing vault.
- All ~22 new unit tests pass.
- The QA multi-round move test (`00i §4`) uses `vault backup` for setup and validates restoration.
- Workflow registry shows `vault-backup` and `vault-restore` workflows after `sgit dev workflow list`.

Estimated effort: ~1 day total (backup ~3h, restore ~5h, tests ~2h, integration with `00i` ~1h, doc/help-text ~30min).
