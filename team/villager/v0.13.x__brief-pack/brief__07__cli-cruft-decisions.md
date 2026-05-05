# Brief B07 — CLI Cruft Decisions + Moves

**Owner:** **Villager Architect** + **Villager Dev** (mechanical moves)
**Status:** **Ready to execute.** Dinis decided option (b) hybrid: vault + share namespaces, no `utils`.
**Estimated effort:** ~½ day
**Touches:** `sgit_ai/cli/CLI__Main.py`, `sgit_ai/cli/CLI__Vault.py`, new `sgit_ai/cli/CLI__Share.py`, tests.

---

## Why this brief exists

22 top-level CLI commands today (down from ~70). Six long-tail commands are still top-level when the original v0.12.x B02 design said they should be namespaced.

**Decided placement (Dinis 2026-05-05):**

| Command | New home | Rationale |
|---|---|---|
| `stash` | **`sgit vault stash <…>`** | Stashing is a vault-state operation (matches `vault rekey`) |
| `remote` | **`sgit vault remote <…>`** | Remotes are vault config |
| `export` | **`sgit vault export`** | Vault snapshot operation |
| `send` | **`sgit share send <…>`** | SG/Send sharing concept |
| `receive` | **`sgit share receive <…>`** | Same |
| `publish` | **`sgit share publish <…>`** | Same |

No `utils` namespace. Final top-level: **16 commands + 10 namespaces** (`branch / history / file / inspect / check / dev / vault / pki / share / show`).

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/changes__cli-inventory.md` — the B02 inventory of all original commands.
3. `sgit_ai/cli/CLI__Main.py` — current registration.
4. Existing namespace handlers (`CLI__Vault.py`, etc.) — the pattern to follow.

---

## Scope

1. For each command moving into a namespace:
   - Move the handler method into the relevant `CLI__<Namespace>` class.
   - Update parser registration in `CLI__Main` from top-level to under-namespace.
   - Update the `_RENAME_MAP` (the friendly-error helper from B02) so old top-level invocations get the right hint.
2. New `share` namespace:
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

- [ ] All 6 moves implemented per the decided placements above.
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
