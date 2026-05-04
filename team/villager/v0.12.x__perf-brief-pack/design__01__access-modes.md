# Design — Access Modes

**Status:** Architecture decision captured. Open sub-question on lazy-history at end.
**Owners:** Architect (design), Dev (implement per brief B09).

## The four modes (as named on the CLI)

| Mode | Top-level command | Working copy | `.sg_vault/` object store | History availability |
|---|---|---|---|---|
| Full | `sgit clone` | full | full | full (all historical trees on disk) |
| Branch (thin) | `sgit clone-branch` | full | HEAD-rooted trees + lazy-fetch | lazy (history-traversal triggers fetch) |
| Headless | `sgit clone-headless` | none | none (or cache-only with `--cache`) | online-only |
| Range | `sgit clone-range <commits>` | full at the range tip | only objects in the requested range | scoped to range |

## The orthogonal `--bare` flag

`--bare` skips the working-copy materialisation but keeps `.sg_vault/`. Combinable with all four flavours:

| Combination | What you get |
|---|---|
| `clone --bare` | full object store, no working copy. Mirror / server-side intermediary. |
| `clone-branch --bare` | HEAD-tree-rooted object store, lazy history. Lightweight mirror. |
| `clone-range --bare` | Range objects only, no working copy. PR-style backup. |
| `clone-headless --bare` | (meaningless — headless is already "no on-disk vault") — error/disallow. |

## Underlying dimensions (for the codebase to internalise)

The four named modes are common combinations of three orthogonal axes. Each command is thin sugar over the dimensional matrix:

| Dimension | Values |
|---|---|
| Working copy | `full` \| `sparse <paths>` \| `none` |
| Object-store completeness | `full` \| `head-rooted` \| `range-rooted` \| `cache-only` \| `none` |
| History availability | `full` \| `lazy` \| `range` \| `online-only` |

This means internally, every clone variant calls the same `Workflow__Clone` (per design D4) parameterised by a small `Schema__Clone__Mode` Type_Safe object. The CLI surface is what's user-facing; the internal model is the matrix.

## Use-case fit

- **`clone`** — default for humans, agents needing full history offline.
- **`clone-branch`** — fast clone for active work; history materialises on demand.
- **`clone-headless`** — CI / ephemeral agents that just want to `cat` a file or `probe` a vault.
- **`clone-range`** — code review / PR-style: pull commits A..B as a self-contained tree.
- **`--bare`** flavours — mirrors, backups, server-side intermediaries.

## Open sub-question (Dinis to confirm)

For `sgit clone-branch`, "full working copy" was decided. The remaining ambiguity:

- **(a) Working copy + commits + HEAD-rooted trees on disk; historical trees lazy-fetch on demand.** Faster clone; `log -p` triggers a fetch on first run.
- **(b) Working copy + commits + ALL historical trees on disk.** Slower clone; `log -p` works fully offline immediately.

Reading (a) gives `clone-branch` real perf wins relative to `clone`. Reading (b) makes `clone-branch` essentially equivalent to `clone` and removes its purpose.

**Recommendation: (a).** That's the only reading where `clone-branch` is a distinct mode worth shipping. Confirm or override.

## Vault-format implications

- Modes 1, 2 and 4 use the same encrypted object store layout (`bare/data/{id}`).
- Mode 4 (range) uses the same layout but only stores a subset.
- Mode 4-headless either has no `.sg_vault/` or only `.sg_vault/local/` for credentials + a small immutable cache.
- The migration command (brief B10) doesn't apply here — these are new commands operating on the existing format. Migration is needed only when server packs (design D5) introduce a new on-disk shape.

## What this design leaves to other docs

- The `--cache` flag for headless: scope and semantics defined in `design__05__clone-pack-format.md` (because headless cache likely IS a pack reference).
- Sparse-clone paths: orthogonal to the four modes; covered by existing v0.10.30 sparse design.
- Workflow steps for each mode: in `design__04__workflow-framework.md`.

## Acceptance for this design

This design is "captured and ready to consume by briefs B03 and B09" when:
- The four named commands + the `--bare` flag are agreed.
- Open sub-question (a)/(b) is resolved.
- Workflow integration is referenced (D4 exists).

Resolution of the sub-question is a one-line edit; do not block downstream design on it.
