# Debrief 05: sgit probe, delete-on-remote, rekey — Vault Lifecycle Commands

**Commits:** `f8d75fa`, `cd07b76`, `5ddd54d`, `b6dfb32`, `143a79e`  
**Date:** April 28, 2026  
**Files changed:** `Vault__Sync.py`, `Vault__API.py`, `CLI__Vault.py`, `CLI__Main.py`, tests

---

## Overview

Three new commands cover the full vault lifecycle beyond the normal init/commit/push/pull loop:
- **`sgit probe`** — identify what a token is before committing to a clone
- **`sgit delete-on-remote`** — destroy vault storage on the server
- **`sgit rekey`** — rotate the encryption key

Together they allow a safe "key rotation" workflow: delete the old vault from the server, rekey locally under a new passphrase, then push to create a fresh vault with no history link to the old one.

---

## `sgit probe`

### Purpose

Answers the question: "what is this token?" without performing a full clone. Returns one of:
- `vault` — token addresses a live sgit vault (has a branch index)
- `share` — token is a Transfer API share link (has transfer metadata)
- `unknown` — not found in either system

### Implementation: `Vault__Sync.probe_token(token_str)`

```
1. Guard: raises RuntimeError if token_str is not a simple token format
   (prevents probing raw passphrases, vault keys, or other non-probe-able strings)

2. Derive vault_id and read_key from the simple token (same derivation as clone)

3. Call batch_read([branch_index_file_id]) — one API call
   If the branch index exists → return {'type': 'vault', 'vault_id': ...}

4. Call API__Transfer.info(transfer_id) — one API call
   If the transfer exists → return {'type': 'share', ...}

5. Return {'type': 'unknown'}
```

Maximum 2 API calls. No vault directory created. No keys written to disk.

### CLI Output

```bash
$ sgit probe coral-equal-1234
  ▸ Checking vault...
  vault  coral-equal-1234  (vault_id: c4958581e0ab)

$ sgit probe test-word-0000
  ▸ Checking vault...
  ▸ Checking transfer...
  unknown  test-word-0000
```

---

## `sgit delete-on-remote`

### Purpose

Permanently destroys all vault data on the server. The local clone is left fully intact on disk — only the server-side objects are deleted. This is a destructive, irreversible server operation.

### Workflow

```bash
$ sgit delete-on-remote
  This will permanently delete vault 'c4958581e0ab' from the server.
  All commits, trees, blobs, and refs will be destroyed.
  Local files and history are NOT affected.

  Type the vault_id to confirm: c4958581e0ab
  ▸ Deleting vault...
  ✓ Deleted 1847 objects.
```

The `--yes` flag skips the confirmation prompt (for automation).

### API Call

`DELETE /api/vault/destroy/{vault_id}` — requires the write key for authorization. The in-memory test stub deletes all keys prefixed `{vault_id}/` from the store and returns `{files_deleted: N}`.

### Implementation Note

`delete-on-remote` intentionally does not remove the local `.sg_vault/` directory or any working-copy files. This makes it safe to use before a `rekey` — the plaintext files on disk are preserved for re-encryption under the new key.

---

## `sgit rekey`

### Purpose

Rotate the vault encryption key. This is not a re-encryption of objects on the server — it's a local reset: wipe `.sg_vault/`, init a new vault with a new key, and commit all files currently in the working directory. History resets to a single initial commit.

### Why No Re-Encryption

Re-encrypting existing objects in place would require decrypting every blob and tree, re-encrypting with the new key, and re-uploading. This is expensive, requires the old key (which may be compromised), and produces a mixed-history vault. The simpler and safer approach: treat the plaintext on disk as the source of truth and rebuild the vault from scratch.

### Workflow

```bash
$ sgit rekey
  ▸ Reading current vault files...  23 files found
  ▸ Wiping .sg_vault/ directory...
  ▸ Initialising new vault...  new vault_id: a7f3c291e80b
  ▸ Committing files...  23 files
  ✓ Vault rekeyed. New vault key:
  my-passphrase:a7f3c291e80b

$ sgit push
  ▸ Uploading objects...
```

Flags:
- `--new-key <passphrase:vault_id>` — specify the new vault key explicitly
- No flag → generates a new random vault_id and prompts for passphrase (or generates one)

### Interactive Wizard: `sgit rekey --interactive`

A step-by-step guided workflow:

```
Step 1/4: Backing up file list...  ✓ (23 files)
Step 2/4: Wiping vault...          ✓
Step 3/4: Generating new key...    ✓ new_key: [displayed]
Step 4/4: Committing files...      ✓ 23 files, 1 commit
```

Also available as individual sub-commands for scripted workflows:
```bash
sgit rekey backup     # writes file list to stdout
sgit rekey wipe       # wipes .sg_vault only
sgit rekey init-new   # inits a fresh vault
sgit rekey commit     # commits working-copy files to new vault
```

### Rekey + Delete Full Rotation Workflow

```bash
sgit delete-on-remote --yes    # remove old vault from server
sgit rekey                     # rebuild locally under new key
sgit push                      # publish under new key
```

After this: the old vault_id is gone from the server, the new vault_id is live with no history link to the old one.

---

## Test Coverage

### `sgit probe` — 11 tests
- `test_probe_vault_token_returns_vault`: in-memory vault exists → type=vault
- `test_probe_share_token_returns_share`: transfer exists → type=share
- `test_probe_unknown_returns_unknown`: neither → type=unknown
- `test_probe_rejects_non_simple_token`: passphrase:vault_id format → RuntimeError
- Edge cases: empty token, too-short token, vault_id format guard

### `sgit delete-on-remote` — 7 tests
- `test_delete_removes_vault_objects`: count decreases after delete
- `test_delete_requires_confirmation`: no --yes → confirmation prompt
- `test_delete_yes_skips_confirmation`: --yes → no prompt
- `test_delete_local_files_preserved`: working copy unchanged after delete
- `test_delete_returns_count`: result dict has `files_deleted` key

### `sgit rekey` — 6 core + 6 corner-case tests
Corner cases:
- `test_rekey_binary_files`: binary content survives rekey round-trip
- `test_rekey_subdirectories`: nested paths preserved
- `test_rekey_empty_vault`: works on vault with no files
- `test_rekey_double_rekey`: two consecutive rekeys work correctly
- `test_rekey_post_push`: rekey followed by push succeeds
- `test_rekey_custom_key`: `--new-key` respected
