# B02 — CLI Restructure: Command Inventory

**Date:** 2026-05-04
**Author:** Villager Dev (Claude Code, SGit-AI__CLI session)
**Status:** Complete

---

## Methodology

Audited every `add_parser` call in `sgit_ai/cli/CLI__Main.py` (78 total).
Each command assigned to one of: TOP-LEVEL, NAMESPACE:<name>, MERGE INTO <other>,
DEFER (placement needs Dinis input before cutting).

---

## Final Assignment Table

| Old top-level command | Decision | New invocation | Notes |
|---|---|---|---|
| `version` | TOP-LEVEL | `version` | Stays |
| `update` | TOP-LEVEL | `update` | Stays |
| `init` | TOP-LEVEL | `init` | Stays |
| `clone` | TOP-LEVEL | `clone` | Stays |
| `status` | TOP-LEVEL | `status` | Stays |
| `commit` | TOP-LEVEL | `commit` | Stays |
| `push` | TOP-LEVEL | `push` | Stays |
| `pull` | TOP-LEVEL | `pull` | Stays |
| `fetch` | TOP-LEVEL | `fetch` | Stays |
| `diff` | NAMESPACE: history | `history diff` | |
| `show` | NAMESPACE: history | `history show` | |
| `log` | NAMESPACE: history | `history log` | |
| `inspect-log` | MERGE INTO | `history log` | Duplicate of `log` |
| `revert` | NAMESPACE: history | `history revert` | |
| `reset` | NAMESPACE: history | `history reset` | |
| `cat` | NAMESPACE: file | `file cat` | |
| `ls` | NAMESPACE: file | `file ls` | |
| `write` | NAMESPACE: file | `file write` | |
| `inspect` | NAMESPACE: inspect | `inspect vault` | Was generic vault overview |
| `inspect-tree` | NAMESPACE: inspect | `inspect tree` | |
| `inspect-object` | NAMESPACE: inspect | `inspect object` | |
| `inspect-stats` | NAMESPACE: inspect | `inspect stats` | |
| `diff-state` | NAMESPACE: inspect | `inspect diff-state` | |
| `dump` | NAMESPACE: dev | `dev dump` | |
| `cat-object` | NAMESPACE: dev | `dev cat-object` | |
| `derive-keys` | NAMESPACE: dev | `dev derive-keys` | |
| `debug` | NAMESPACE: dev | `dev debug` | |
| `info` | NAMESPACE: vault | `vault info` | |
| `probe` | NAMESPACE: vault | `vault probe` | |
| `delete-on-remote` | NAMESPACE: vault | `vault delete-on-remote` | |
| `rekey` | NAMESPACE: vault | `vault rekey` | + subcommands |
| `uninit` | NAMESPACE: vault | `vault uninit` | |
| `clean` | NAMESPACE: vault | `vault clean` | |
| `share` | NAMESPACE: vault | `vault share` | per design__02 |
| `fsck` | NAMESPACE: check | `check fsck` | |
| `branches` | MERGE INTO | `branch list` | Duplicate of `branch list` |
| `switch` | NAMESPACE: branch | `branch switch` | |
| `merge-abort` | NAMESPACE: branch | `branch merge-abort` | |
| `checkout` | NAMESPACE: branch | `branch checkout` | |
| `stash` | DEFER | `stash` (stays) | Design TBD; has sub-subcommands |
| `send` | DEFER | `send` (stays) | Messaging namespace TBD |
| `receive` | DEFER | `receive` (stays) | Messaging namespace TBD |
| `publish` | DEFER | `publish` (stays) | Placement TBD |
| `export` | DEFER | `export` (stays) | Placement TBD |
| `remote` | STAYS NAMESPACE | `remote` | Already namespaced |
| `pki` | STAYS NAMESPACE | `pki` | Already namespaced |
| `branch` | STAYS NAMESPACE | `branch` | Already namespaced; gains subcommands |
| `vault` (cred store) | STAYS NAMESPACE | `vault` | Expands to include operational cmds |
| `dev` | STAYS NAMESPACE | `dev` | B01; gains more subcommands |

---

## Top-level count post-B02

**Primitives (9):** version, update, init, clone, status, commit, push, pull, fetch

**Namespaces (9):** branch, history, file, vault, inspect, dev, check, remote, pki

**Deferred top-level (4):** stash, send, receive, publish, export
(Noted as temporary; will be assigned in a follow-on brief once Dinis decides on
the messaging / sharing namespace structure.)

Post-B03 the four clone-family + `create` commands will bring primitives to 14,
meeting the design__02 "~14 + ~8 namespaces" target.

---

## Open items for Dinis

1. **`send` / `receive` / `publish` / `export`** — where do these live?
   Options: (a) `vault share/send/receive/publish/export`; (b) own top-level namespace
   `messaging <…>` or `transfer <…>`; (c) stay top-level as primitives.
   Currently deferred as top-level.

2. **`stash`** — `vault stash` or stay top-level? Currently deferred since stash has
   its own pop/list/drop sub-subcommands and design__02 doesn't assign it explicitly.

---

## Rename map (data-driven; used for friendly-error hints)

37 renames registered in `CLI__Main._RENAME_MAP`. Any invocation of an old name
prints: `sgit: '<old>' has moved to 'sgit <new>'.` and exits 1.

*— Claude Code, SGit-AI__CLI session | 2026-05-04*
