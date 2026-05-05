# Brief B07 — CLI Cruft Decisions + Moves

**Owner:** **Architect** (decisions with Dinis input) + **Designer** (UX) + **Villager Dev** (mechanical moves)
**Status:** **Blocked on Dinis decision.** Not ready to launch as a Sonnet brief until Dinis answers the open question below.
**Estimated effort:** ~½ day after decisions are made
**Touches:** `sgit_ai/cli/CLI__Main.py`, possibly new `sgit_ai/cli/CLI__Share.py`, tests.

---

## Why this brief exists

22 top-level CLI commands today (down from ~70). Six long-tail commands are still top-level when the original v0.12.x B02 design said they should be namespaced:

| Top-level | Possible homes |
|---|---|
| `stash` | `vault stash <…>` (rare op) OR stay top-level (frequent enough?) |
| `remote` | `vault remote <…>` |
| `send` | new `share <…>` namespace OR `vault send <…>` |
| `receive` | new `share <…>` namespace OR `vault receive <…>` |
| `publish` | new `share <…>` namespace OR `vault publish <…>` |
| `export` | `vault export` OR top-level (Git compat) |

These need product-level decisions before a brief can execute.

---

## Decision needed from Dinis

For each of the six commands above, pick a destination:
- `stash` → ?
- `remote` → ?
- `send` → ?
- `receive` → ?
- `publish` → ?
- `export` → ?

**Recommended placements** (just opinions; Dinis decides):

- **`stash` → `vault stash <…>`** (rare-ish op; matches `vault rekey`).
- **`remote` → `vault remote <…>`** (vault-level configuration; clear home).
- **`send` / `receive` / `publish` → `share <…>`** as a NEW top-level namespace (these are a coherent message-passing concern and naming them under `vault` confuses; `share` reads naturally).
- **`export` → top-level** (Git users expect `git archive`; `sgit export` matches).

Net effect after these moves: top-level goes from 22 → 17, with a new `share` namespace.

---

## Required reading (when unblocked)

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/changes__cli-inventory.md` — the B02 inventory of all original commands.
3. `sgit_ai/cli/CLI__Main.py` — current registration.
4. Existing namespace handlers (`CLI__Vault.py`, etc.) — the pattern to follow.

---

## Scope (post-decision)

1. For each command moving into a namespace:
   - Move the handler method into the relevant `CLI__<Namespace>` class.
   - Update parser registration in `CLI__Main` from top-level to under-namespace.
   - Update the `_RENAME_MAP` (the friendly-error helper from B02) so old top-level invocations get the right hint.
2. If `share` becomes a new top-level namespace:
   - Create `sgit_ai/cli/CLI__Share.py` with `cmd_send`, `cmd_receive`, `cmd_publish`.
   - Register `share` parser in `CLI__Main` with subparsers.
   - Update `_RENAME_MAP` for the three commands.
3. Tests: existing `send / receive / publish / stash / remote / export` tests pass under the new names. Add wrong-context error tests for the six renamed commands.

---

## Hard rules

- **Behaviour preservation per command** — handlers do the same thing, just at a different command path.
- **Friendly error on old top-level invocation** — same pattern B02 established.
- **Type_Safe metadata** for `visible_in` on every command (per B04 design D3).
- **No mocks.**
- **Coverage must not regress.**

---

## Acceptance criteria

- [ ] Dinis has decided placement for each of the 6 commands.
- [ ] All 6 moves implemented per the decision.
- [ ] Friendly-error rename map updated.
- [ ] Tests pass under the new command paths.
- [ ] Wrong-context error fires for each renamed command.
- [ ] Final top-level count ≤ 18.

---

## When done

Return a ≤ 200-word summary:
1. Final placement per command.
2. Top-level count before / after.
3. New `share` namespace shipped (or not, per decision).
4. Test count + coverage delta.
