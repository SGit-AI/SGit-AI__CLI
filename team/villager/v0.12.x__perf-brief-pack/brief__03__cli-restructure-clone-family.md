# Brief B03 — CLI Restructure: Clone Family + `create`

**Owner role:** **Villager Architect** (design) + **Villager Dev** (implementation)
**Status:** Ready to execute. Independent of B01–B02.
**Prerequisites:** None hard. Best after B02 lands so the new top-level layout is in place.
**Estimated effort:** ~4–6 hours
**Touches:** `sgit_ai/cli/CLI__Main.py`, new clone-family handlers, tests. **Per decision 6 + 7: four clone commands + `create`.**

---

## Why this brief exists

Per `design__01__access-modes.md` + `design__02__cli-command-surface.md`,
the top-level surface gains 5 commands:

| Command | Purpose | Status |
|---|---|---|
| `create` | init + create remote + publish (one-shot) | NEW |
| `clone` | full clone (default) | EXISTS — keep |
| `clone-branch` | thin clone (HEAD-rooted, lazy history) | NEW (stub now, full impl in B09) |
| `clone-headless` | online-only clone | NEW (stub now, full impl in B09) |
| `clone-range <range>` | clone a commit range | NEW (stub now, full impl in B09) |

Plus the orthogonal `--bare` flag combinable with `clone`, `clone-branch`, `clone-range`.

---

## Required reading

1. This brief.
2. `design__01__access-modes.md` (the four modes + `--bare`).
3. `design__02__cli-command-surface.md` (top-level tree).
4. `team/villager/architect/architect__ROLE.md` and `team/villager/dev/dev__ROLE.md`.
5. `sgit_ai/cli/CLI__Main.py` clone parser registration.
6. `sgit_ai/sync/Vault__Sync.py` `_clone_with_keys` (the existing implementation).

---

## Scope

### Step 1 — `create` command

`sgit create <vault-name>` does:
1. `init` locally (existing path).
2. Create remote vault on the server (existing API endpoint should support this; if not, escalate to Architect).
3. Publish the empty initial commit.
4. Save credentials locally.
5. Print the new vault key + read-key for sharing.

The end state is identical to: `sgit init && sgit remote add … && sgit push`. `create` is the one-shot version.

### Step 2 — Clone-family commands

**`clone`**: existing, no behaviour change yet. Add `--bare` flag with not-yet-implemented stub error if not yet wired (or wire to a no-working-copy variant if trivial).

**`clone-branch`**: NEW top-level command. **Stub implementation** that prints:
```
clone-branch: full implementation lands in brief B09 (per-mode clone).
For now, run `sgit clone <vault-key> <dir>` for full clone.
```
Stub only. The CLI surface is established now so other briefs can target it.

**`clone-headless`**: NEW top-level command. Stub same way.

**`clone-range <vault-key>:<commit-range> <dir>`**: NEW top-level command. Stub same way.

The point of this brief is: lock in the user-facing CLI surface. The actual mode-specific logic lands in brief B09. The stubs make the CLI tree complete and testable.

### Step 3 — `--bare` flag

Add `--bare` as a boolean flag on `clone`, `clone-branch`, `clone-range`. For `clone --bare`, wire it to call `_clone_with_keys` with a new `materialize_working_copy: bool` parameter (default True). The new parameter threads through to skip the working-copy extraction phase. (If the current Phase-9 extraction is cleanly separable, this is a small change.) For `clone-branch --bare` and `clone-range --bare`, just add the flag; the brief B09 implementations will honour it.

`clone-headless --bare` is meaningless — error friendly: "headless is already bare-equivalent; --bare flag rejected".

### Step 4 — Tests

- New tests under `tests/unit/cli/test_CLI__Create.py` for `create`.
- New tests under `tests/unit/cli/test_CLI__Clone_Family.py` for each new command (stubs error correctly, `--bare` parses, friendly errors fire).
- Refresh existing clone tests for any signature changes.

---

## Hard constraints

- **No mocks.** Real in-memory transfer server.
- **No `__init__.py` under `tests/`.**
- **Type_Safe metadata** for `visible_in` on every new command (per design D3).
- **Backward compat: NONE for command names** (decision 2). But: existing `clone` command behaviour is unchanged.
- Suite must pass under Phase B parallel CI shape.
- Coverage must not regress.

---

## Acceptance criteria

- [ ] `sgit create <vault-name>` creates a fully-published vault end-to-end (works against the in-memory server).
- [ ] `sgit clone-branch`, `sgit clone-headless`, `sgit clone-range` exist as top-level commands. Stubs error friendly with a pointer to brief B09.
- [ ] `clone --bare`, `clone-branch --bare`, `clone-range --bare` parse cleanly. `clone --bare` either works or stubs to a clear "not yet implemented" with B09 reference.
- [ ] `clone-headless --bare` errors friendly: "redundant flag".
- [ ] At least 4 tests for `create` (happy + 3 edge cases).
- [ ] At least 2 tests per new clone-family command (parsing + stub message).
- [ ] Suite ≥ existing test count + N passing; coverage delta non-negative.

---

## Out of scope

- Implementing the lazy-history fetch path for `clone-branch` (brief B09).
- Implementing the headless mode (brief B09).
- Implementing the commit-range walker for `clone-range` (brief B09).
- Server-side pack consumption (brief B08 + B09).
- Workflow-framework refactor of `clone` (brief B06).

---

## Deliverables

1. New `sgit_ai/cli/CLI__Create.py` (or method on existing CLI__Vault).
2. Updates to `sgit_ai/cli/CLI__Main.py` for new top-level commands + `--bare` flag.
3. Possibly small additive change to `_clone_with_keys` for `materialize_working_copy` parameter (or stub-equivalent if cleaner).
4. Test files.

---

## When done

Return a ≤ 250-word summary:
1. Top-level commands added.
2. `--bare` wiring status (working / stubbed).
3. `create` end-to-end behaviour confirmation.
4. Test count delta + coverage delta.
5. Any escalation to Architect (e.g., if `create` needs a new server endpoint).
