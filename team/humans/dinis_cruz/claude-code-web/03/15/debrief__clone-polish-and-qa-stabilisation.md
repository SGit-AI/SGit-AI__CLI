# Debrief — Clone Polish & QA Stabilisation

**Date:** 2026-03-15
**Branch:** `claude/create-villager-team-7wpYl`

## What We Did

This session focused on stabilising the sg-send-cli after the core `init / commit / push / pull / clone` workflow was already functional. We tackled bugs surfaced by QA tests and added user-facing polish.

### 1. Fixed CLI Commit Syntax & QA Test Failures
- Fixed issues in the CLI commit flow that were causing QA walkthrough tests to fail.
- Ensured the full `init → commit → push` pipeline works end-to-end against the real SG/Send server.

### 2. Fixed Clone Crash on None Directory
- `clone` was crashing when no target directory was provided (defaulting to `None`).
- Fixed the fallback so it correctly uses the vault ID as the directory name.
- Added diagnostic output to QA tests for easier debugging.

### 3. Unique Vault IDs Per Test Run
- QA tests were polluting each other by reusing the same vault ID across runs.
- Each test now generates a unique vault ID (using a UUID suffix), preventing server-side state conflicts between test runs.

### 4. Git-Like Progress Output
- Created `CLI__Progress` — a new Type_Safe class that renders git-style progress bars and status lines.
- Wired progress output into `clone`, `push`, and `pull` commands.
- Clone now shows: key derivation → structure download → object download (with progress bar) → branch setup → working copy extraction.
- Push shows: encryption → upload (with progress bar) → branch update.
- Pull shows: fetch → download (with progress bar) → merge → extraction.

### 5. All Tests Green
- Ran the full test suite across 6 parallel test groups (unit, QA walkthrough, QA clone, integration sync, integration crypto, integration API).
- All passed.

## Key Files Changed

| File | What |
|------|------|
| `sg_send_cli/cli/CLI__Progress.py` | New — git-style progress rendering |
| `sg_send_cli/cli/CLI__Vault.py` | Wired progress into clone/push/pull |
| `sg_send_cli/sync/Vault__Sync.py` | Progress callbacks, clone directory fix |
| `sg_send_cli/cli/CLI__Token_Store.py` | Minor fix for token handling |
| `tests/qa/test_QA__Vault_Walkthrough.py` | Unique vault IDs, diagnostic improvements |
| `tests/qa/test_QA__Vault_Init_Walkthrough.py` | Unique vault IDs, diagnostic improvements |

## End State

The CLI now supports the full git-like workflow with polished output:

```
$ sg-send-cli clone {vault_key}
Cloning into 'rw7hxbqn'...
  ▸ Deriving vault keys
  ▸ Downloading vault structure
  ▸ Downloading [████████████████████] 15/15
  ▸ Loading branch index
  ▸ Creating clone branch
  ▸ Registering clone branch on remote (3 objects)
  ▸ Setting up local config
  ▸ Extracting working copy (1 files)
Cloned into rw7hxbqn/
```

All tests pass. Ready for merge.
