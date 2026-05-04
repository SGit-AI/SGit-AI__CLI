# Brief B02 — CLI Restructure: Namespaces

**Owner role:** **Villager Architect** (inventory + decisions) + **Villager Dev** (implementation)
**Status:** Ready to execute. Independent of B01.
**Prerequisites:** None.
**Estimated effort:** ~6–8 hours
**Touches:** `sgit_ai/cli/CLI__Main.py`, `sgit_ai/cli/` sub-modules, tests under `tests/unit/cli/`. **Per decision 2: NO backward-compat aliases.** Hard cut.

---

## Why this brief exists

Today: ~70 top-level commands (the v0.11.x count of 67 plus the
Brief-05 surgical-write surface added in v0.12.0). Per
`design__02__cli-command-surface.md`, the target is ~14 primitives +
8 namespaces. Brief B02 does the move: existing `inspect-*` family →
`sgit inspect <…>`; existing dev/debug → `sgit dev <…>`;
`log`/`diff`/`show`/`blame` → `sgit history <…>`; `cat`/`ls`/`write` →
`sgit file <…>`; `rekey`/`probe`/`delete-on-remote`/`info`/`wipe` →
`sgit vault <…>`; `branch <list|create|switch|delete|rename>`;
`fsck`/`verify`/`sign` → `sgit check <…>`.

`pki` is already namespaced.

**Post-v0.12.0 inventory note.** v0.12.0 added these top-level
commands as part of Brief 05 (surgical-write CLI):
- `write` — surgical single-file write (→ `sgit file <…>` namespace)
- `cat` — already existed but now has `--id` and `--json` flags (→ `sgit file <…>`)
- `ls` — already existed but now has `--ids` and `--json` flags (→ `sgit file <…>`)
- `clone --read-key` flag (stays on `clone`, since it's a clone variant)
- `derive-keys` — now accepts `read_key:vault_id` format (→ `sgit dev <…>` candidate; user-facing or dev?)
- `info` — now reports write-key availability (→ `sgit vault <…>` candidate)

Re-run the audit-grep below against the current `CLI__Main.py` to get
the exact list before starting the move.

---

## Required reading

1. This brief.
2. `design__02__cli-command-surface.md` (the canonical tree).
3. `design__03__context-aware-visibility.md` (visibility metadata model).
4. `team/villager/architect/architect__ROLE.md` and `team/villager/dev/dev__ROLE.md`.
5. `sgit_ai/cli/CLI__Main.py` — current registration. Audit-grep:
   ```
   grep -n add_parser sgit_ai/cli/CLI__Main.py | wc -l
   ```

---

## Process

### Step 1 — Inventory (Architect)

Categorise every existing top-level command into one of:
- TOP-LEVEL (stays at top — primitive)
- NAMESPACE: <name> (moves into a namespace)
- DELETE (no longer needed; e.g. duplicates)
- MERGE INTO <other> (folded into another command)

Produce `team/villager/v0.12.x__perf-brief-pack/changes__cli-inventory.md` with the full mapping. Include the cruft inventory listed in `design__02` §"Top-level cruft inventory".

### Step 2 — Implementation (Dev)

For each namespace:
- Create a `CLI__<Namespace>` class (e.g., `CLI__Inspect`, `CLI__History`, `CLI__File`, `CLI__Vault`, `CLI__Dev`, `CLI__Check`).
- Move handler methods from the existing top-level into the new class.
- Register a single top-level subparser per namespace; subcommands live under the namespace's own parser.
- **No backward-compat aliases.** Old top-level invocations error with a friendly hint:
  ```
  sgit: 'inspect-tree' has moved to 'sgit inspect tree'.
  ```
  The error mapper is data-driven (one dict mapping old → new) so adding aliases later is trivial if Dinis changes his mind.
- Each command carries Type_Safe metadata for `visible_in` (per `design__03`); `visible_in` defaults are conservative — brief B04 wires the runtime filtering.

### Step 3 — Tests

For each moved command:
- Existing test that called `cmd_<name>` directly: keep, refactor invocation if signature changed.
- New test that the friendly-error mapper fires for the old top-level invocation.
- New test that the new namespaced invocation works end-to-end.

---

## Hard constraints

- **No `__init__.py` under `tests/`** (project rule).
- **No mocks.** Real argparse parsers, real CLI invocations.
- **Behaviour preservation per command.** Each individual command's output bytes are unchanged when invoked under the new name. Brief B03 introduces *new* commands; B02 only restructures existing ones.
- **No deprecation aliases.** Hard cut. Friendly error suggests the new name.
- Coverage must not regress.
- Suite must pass under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Inventory doc exists at `changes__cli-inventory.md`.
- [ ] Top-level command count is between 13 and 18 (excluding namespaces themselves).
- [ ] Every namespace listed in design D2 §"Namespace contents" exists and has its commands.
- [ ] Friendly-error mapper fires for every renamed command with the correct new-name suggestion.
- [ ] Tests for at least one happy-path + one friendly-error per renamed command.
- [ ] Suite ≥ existing test count + N passing; coverage delta non-negative.
- [ ] Visibility metadata declared on every command (default sets are fine; B04 refines).

---

## Out of scope

- The new clone-family commands (`clone-branch`, `clone-headless`, `clone-range`) — brief B03.
- Context-aware visibility runtime — brief B04.
- Adding new commands beyond reorganisation.
- Source changes in `sgit_ai/sync/`, `crypto/`, `objects/` etc.

---

## Deliverables

1. Inventory doc.
2. New `sgit_ai/cli/CLI__<Namespace>.py` files (one per namespace).
3. Refactored `sgit_ai/cli/CLI__Main.py` with the new top-level surface.
4. Tests under `tests/unit/cli/`.

---

## When done

Return a ≤ 250-word summary:
1. Final top-level count + namespace count.
2. Number of commands moved + number deleted/merged.
3. Test count delta + coverage delta.
4. Any inventory item that needed Architect+Dinis discussion.
5. Anything you couldn't fit (escalate as a follow-up brief).
