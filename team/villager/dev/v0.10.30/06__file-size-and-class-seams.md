# Finding 06 — File Size and Natural Class-Split Seams

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** major (architecture-level)
**Owners:** **Architect** — Villager Dev does NOT split, only flags.

---

## LOC measurements (current branch)

| File | LOC | Sprint delta |
|------|----:|-------------:|
| `sgit_ai/sync/Vault__Sync.py` | **2986** | grew significantly (added: `write_file`, `delete_on_remote`, `rekey*` x5, `probe_token`, `_clone_resolve_simple_token`, `_load_push_state`, `_save_push_state`, `_clear_push_state`, `sparse_ls`, `sparse_cat`, `sparse_fetch`, `_get_head_flat_map`, `_clone_download_blobs`, etc.) |
| `sgit_ai/cli/CLI__Vault.py` | **1381** | grew by 11 new `cmd_*` methods |
| `sgit_ai/cli/CLI__Main.py` | 767 | grew (probe / write / fetch / cat / ls / rekey* / delete-on-remote parsers) |
| `sgit_ai/sync/Vault__Storage.py` | 102 | unchanged shape, +1 method (`clone_mode_path`) |
| `sgit_ai/crypto/Vault__Crypto.py` | (modified) | +2 methods (`encrypt_deterministic`, `encrypt_metadata_deterministic`) |

`Vault__Sync.py` at 2986 LOC is the single biggest source file in the
project and has now passed the practical threshold for ergonomic
review. v0.5.11 already flagged this module as the deep-audit's
largest finding; the sprint has worsened it.

`CLI__Vault.py` at 1381 LOC is a single class with 47 `cmd_*` methods.
Each `cmd_*` is small (10–80 lines) but they share `args` parsing
patterns, JSON-output patterns, and read-only guarding patterns.

## Natural seams identified (for Architect review)

### `Vault__Sync` — 8 candidate sub-classes

A non-binding map of seams. **Do not refactor without Architect
sign-off.**

| Sub-class | Methods (current `Vault__Sync.py` line ranges) |
|-----------|------------------------------------------------|
| `Vault__Sync__Init` | `init`, `generate_vault_key`, `_init_components` (~58–155) |
| `Vault__Sync__Commit` | `commit`, `_generate_commit_message`, `write_file` (155–335) |
| `Vault__Sync__Reset` | `reset` (337–397) |
| `Vault__Sync__Status` | `status`, `_get_head_flat_map` (397–571, 2044–2074) |
| `Vault__Sync__Pull` | `pull`, `_clone_download_blobs` (572–800, 1957–2042) |
| `Vault__Sync__Push` | `push` and helpers (801–1131) |
| `Vault__Sync__Clone` | `clone`, `_clone_with_keys`, `_clone_resolve_simple_token`, `clone_read_only`, `clone_from_transfer` (1252–1722) |
| `Vault__Sync__Rekey_Probe` | `delete_on_remote`, `rekey*` x5, `probe_token` (1724–1837) |
| `Vault__Sync__Sparse` | `sparse_ls`, `sparse_fetch`, `sparse_cat` (2075–2214) |

A `Vault__Sync` facade can compose these and preserve the public API
(important for CLI consumers).

### `CLI__Vault` — 4 candidate sub-classes

| Sub-class | `cmd_*` methods |
|-----------|-----------------|
| `CLI__Vault__Lifecycle` | clone, init, uninit, status, commit, pull, push, reset |
| `CLI__Vault__Branching` | branches, merge_abort, remote_*, checkout |
| `CLI__Vault__Rekey` | probe, delete_on_remote, rekey*, derive_keys |
| `CLI__Vault__Inspect` | info, fsck, log, ls, fetch, cat, write, inspect_*, cat_object |

Each sub-class would inherit a shared base providing `_check_read_only`,
`_resolve_token_and_url`, `_emit_json`, etc.

## Risk if not split

- Any change in `Vault__Sync.py` requires re-reading thousands of
  lines to understand interactions (e.g., `write_file` vs. `commit`
  share `_generate_commit_message`; rekey reuses `commit`; probe
  reuses `_clone_resolve_simple_token` patterns).
- Test-file size grows in lock-step (`test_Vault__Sync__*.py` already
  has 11 separate files for the same `Vault__Sync` class).
- New features land at the bottom of the file by gravity, increasing
  the chance of accidental ordering coupling.

## Severity rationale

**major (architecture)** — not a bug, but an erosion of maintainability.
v0.5.11 baseline already flagged this. Going from ~2400 LOC (v0.5.11)
to 2986 LOC in one sprint is a 25% growth in the worst file in the
codebase. Recommend the next Phase 3 sprint allocate explicit time
for the Architect-owned class-split.

## Suggested next-action owner

- **Architect** — owns the boundary decision. Recommend producing a
  `team/villager/architect/v0.10.30__plan__class-split.md` after
  reviewing this finding.
- **Villager Dev** — stands by to execute mechanical extracts once
  Architect produces the seam map.
