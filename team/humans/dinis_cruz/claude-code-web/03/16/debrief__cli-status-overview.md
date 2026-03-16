# Technical Debrief — sg-send-cli Status Overview

**Date:** 2026-03-16
**Version:** v0.8.2
**Branch:** `claude/create-villager-team-7wpYl`

---

## What sg-send-cli Is

A Python CLI tool that implements "git for encrypted vaults." All data is encrypted client-side with AES-256-GCM before touching the network. The sync model uses content-addressed objects, commit chains, branch refs, and 3-way merge — closely mirroring git's internals.

---

## What Currently Works

### Core Workflow (end-to-end tested)

| Command | Status | Description |
|---------|--------|-------------|
| `init` | Working | Create new vault, register on server, set up bare structure + named/clone branches |
| `commit` | Working | Scan working dir, encrypt changed files, create signed commit with tree + parent chain |
| `push` | Working | Delta upload (only new objects), CAS on ref, fetch-first pattern, batch API |
| `pull` | Working | Fetch remote, find LCA, 3-way merge, extract working copy |
| `clone` | Working | Download vault from server, create clone branch, extract working copy |
| `status` | Working | Diff working dir against last commit (added/modified/deleted) |
| `branches` | Working | List all branches with type and HEAD commit |
| `merge-abort` | Working | Restore pre-merge state, remove conflict files |

### PKI System (fully functional)

| Command | Status | Description |
|---------|--------|-------------|
| `pki keygen` | Working | Generate RSA-4096 (encryption) + ECDSA P-256 (signing) key pair |
| `pki list` | Working | List local key pairs with fingerprints |
| `pki export/import` | Working | Share public key bundles between users |
| `pki contacts` | Working | List imported contacts |
| `pki sign/verify` | Working | Detached ECDSA signatures |
| `pki encrypt/decrypt` | Working | Hybrid RSA-OAEP + AES-256-GCM encryption for recipients |

### Remote & Auth Management

| Command | Status | Description |
|---------|--------|-------------|
| `remote add/remove/list` | Working | Manage remote endpoints per vault |
| `vault add/list/remove/show` | Working | Encrypted credential store (`~/.sg-send/vaults.enc`) |
| Token auto-save | Working | `--token` saved to `.sg_vault/token` on first use |

### Inspection & Debug Tools

| Command | Status | Description |
|---------|--------|-------------|
| `inspect` | Working | Vault metadata overview |
| `inspect-object` | Working | Decrypt and show object details |
| `inspect-tree` | Working | List current tree entries |
| `inspect-log` / `log` | Working | Commit history with `--oneline` and `--graph` modes |
| `cat-object` | Working | Decrypt and display raw object contents |
| `inspect-stats` | Working | Object store statistics |
| `derive-keys` | Working | Show all derived keys for a vault key |
| `checkout` / `clean` | Working | Extract/remove working copy from bare vault |

### UX Polish

- Git-style progress bars during clone/push/pull (via `CLI__Progress`)
- Interactive prompts for token/URL on first push
- `--version` flag

---

## Architecture Summary

```
CLI Layer          → CLI__Main, CLI__Vault, CLI__PKI, CLI__Progress
                     (argparse commands, progress rendering)
                          │
Sync Engine        → Vault__Sync (orchestrator)
                     ├── Vault__Fetch       (remote state download)
                     ├── Vault__Merge       (3-way tree merge)
                     ├── Vault__Batch       (atomic batch operations)
                     ├── Vault__Change_Pack (pending file bundles)
                     ├── Vault__GC          (drain pending → committed)
                     └── Vault__Branch_Manager (named + clone branches)
                          │
Object Layer       → Vault__Object_Store   (bare/data/obj-*)
                     Vault__Ref_Manager     (bare/refs/ref-*)
                     Vault__Commit          (create/load/sign commits)
                          │
Crypto Layer       → Vault__Crypto         (AES-256-GCM, PBKDF2, HKDF, HMAC)
                     PKI__Crypto            (RSA-OAEP, ECDSA P-256, hybrid enc)
                     Vault__Key_Manager     (branch key pair storage)
                          │
API Layer          → Vault__API            (read/write/delete/batch/list)
                     (talks to SG/Send Transfer API)
```

### Crypto Guarantees

- All vault data encrypted client-side with AES-256-GCM
- Key derivation: PBKDF2-SHA256 (600k iterations) → read_key + write_key
- Per-file keys via HKDF-SHA256
- Commit signing via ECDSA P-256
- **Web Crypto interop:** all primitives match browser output byte-for-byte

### Sync Model

- **Content-addressed objects** — deduplication via SHA256[:12]
- **Commit chains** — immutable, with tree snapshots and parent pointers
- **Named branch** — shared state (like `main`)
- **Clone branch** — local working copy (like a feature branch)
- **CAS on push** — compare-and-swap prevents lost updates
- **3-way merge** — automatic when possible, conflict files when not
- **Batch API** — atomic multi-object push

---

## Test Health

| Suite | Tests | Status |
|-------|-------|--------|
| Unit tests | 971 pass, 4 xfail | Green |
| QA walkthroughs | 46 methods (4 files) | Requires local server |
| Integration tests | 34 methods (3 files) | Requires Python 3.12 venv |

### 4 Known Bugs (xfail)

| Bug | Impact | Severity |
|-----|--------|----------|
| Second pull after cross-clone merge reports "merged" instead of "up_to_date" | Cosmetic — merge is correct but status is wrong | Medium |
| File deletion doesn't propagate across clones | Deleted files reappear after pull | High |
| Modifying a pulled file triggers false merge conflict | Blocks legitimate edits after pull | High |
| Push silently succeeds when remote writes fail | **Data loss risk** — user thinks push completed | Critical |

---

## What We Fixed Today (2026-03-16)

### Browser-Compatible Dual-Writes

**Problem:** Vaults created via the CLI returned 404 when opened in the browser. The browser derives deterministic HMAC-based file IDs; the CLI was writing to UUID-based `bare/` paths.

**Fix:** Added dual-writes at every push path so both the CLI's internal structure and the browser-expected HMAC-derived paths are populated:

| File | Change |
|------|--------|
| `Vault__Crypto.py` | Added `derive_branch_index_file_id()`, `BRANCH_INDEX_DOMAIN`, updated `derive_keys()` |
| `Vault__Batch.py` | Ref dual-write to HMAC-derived path during batch push |
| `Vault__Sync.py` | Ref + index dual-writes in `_register_pending_branch()` and `_upload_bare_to_server()` |

---

## What Needs to Be Done Next

### Critical (blocking production)

1. **Fix push silent failure on remote write error** — the CLI currently doesn't detect when the API returns an error during push. Users think their data is saved when it isn't.

2. **Fix file deletion propagation** — deleting a file in one clone and pushing doesn't propagate the deletion when another clone pulls. The file reappears.

3. **Fix false merge conflicts after pull** — editing a file that was just pulled triggers a false conflict, blocking the push.

### Important (pre-release)

4. **Validate browser payload format** — confirm the encrypted ref/index format the CLI writes matches what the browser's vault-open parser expects (JSON schema, encryption wrapping).

5. **Migration for existing vaults** — vaults created before the dual-write fix still have data only at `bare/` paths. Need a one-time server-side or CLI-driven migration to copy to HMAC-derived paths.

6. **Fix pull status after merge** — second pull incorrectly reports "merged" when it should be "up_to_date".

### Nice to Have

7. **CI for QA tests** — currently require manual local server startup; should run in CI with docker-compose.
8. **Coverage reporting** — no pytest-cov numbers being tracked.
9. **Stress testing** — large file counts, deep directory trees, concurrent multi-user scenarios.
10. **Long-term dual-write decision** — vault team needs to decide if both sides converge on HMAC-derived IDs or keep dual-write permanently.
