# Brief B04 — Context-Aware Command Visibility (Implementation)

**Owner role:** **Villager Dev** (`team/villager/dev/dev__ROLE.md`)
**Status:** Ready to execute. Best after B02 + B03 land (CLI tree settled).
**Prerequisites:** B02 + B03 merged.
**Estimated effort:** ~4–6 hours
**Touches:** `sgit_ai/cli/`, new `sgit_ai/sync/Vault__Context.py`, tests.

---

## Why this brief exists

Per `design__03__context-aware-visibility.md` + decision 9: only show / accept commands that make sense in the current context. Inside a vault, hide the clone family. Outside one, hide commit/push/pull. Wrong-context invocations get a friendly error (not "unknown command"). Tab completion respects context.

---

## Required reading

1. This brief.
2. `design__03__context-aware-visibility.md` (the model + tables).
3. `team/villager/dev/dev__ROLE.md`.
4. `sgit_ai/cli/CLI__Main.py` after briefs B02 + B03 have landed.
5. Existing context-detection helpers in `sgit_ai/sync/` (vault root discovery added during v0.10.30 — re-use this).

---

## Scope

### Step 1 — Context detector

Add `sgit_ai/sync/Vault__Context.py`:

```python
class Enum__Vault_Context_State(Enum):
    OUTSIDE         = 'outside'
    INSIDE_WORKING  = 'inside-working'
    INSIDE_BARE     = 'inside-bare'

class Vault__Context(Type_Safe):
    state            : Enum__Vault_Context_State
    vault_path       : Safe_Str__File_Path = None
    vault_id         : Safe_Str__Vault_Id  = None
    has_working_copy : bool

    @classmethod
    def detect(cls, cwd: Safe_Str__File_Path) -> 'Vault__Context':
        # walk parents looking for .sg_vault/
        # if found + working tree present → INSIDE_WORKING
        # if found + no working tree    → INSIDE_BARE
        # else → OUTSIDE
        ...

    @classmethod
    def detect_with_override(cls, cwd, vault_path_arg) -> 'Vault__Context':
        ...
```

Re-use the v0.10.30 vault-root-discovery helpers. No new walk implementation if one already exists.

### Step 2 — Visibility metadata

Each top-level command (and namespace) declares `visible_in: list[Enum__Vault_Context_State]` as a Type_Safe attribute. Brief B02 already added defaults; this brief replaces defaults with real values from the table in design D3 §"Visibility per context".

### Step 3 — Argparse tree per context

`CLI__Main` builds the argparse tree based on `Vault__Context.detect(os.getcwd())`. Only commands visible in the current context get registered as visible subparsers. The "full" surface stays in a hidden `_all_commands` list used by `sgit help all`.

For wrong-context invocation, install a custom argparse error handler that:
1. Looks up the attempted command in `_all_commands`.
2. If found and not visible: emits the friendly error (per design D3 §"Wrong-context invocation").
3. If not found: standard "unknown command" error.

### Step 4 — Help output

- `sgit` (no args) → `print_help()` honours visibility.
- `sgit help` → same.
- `sgit help all` → prints the full surface, regardless of context.
- `sgit help <cmd>` → works for any command.

### Step 5 — Global `--vault PATH` flag

Add a top-level `--vault PATH` flag that overrides context detection. When passed, the detector reports the override path's context. Useful for power users / scripts.

### Step 6 — Tab completion

If the project has shell completion scripts, regenerate them for the per-context surface. If not, this is out of scope (separate DevOps brief later).

### Step 7 — Tests

- Detector tests: `tmp_path` setups for each of the three contexts; assert correct detection.
- Visibility tests: invoke `sgit help` from different contexts; assert visible commands match expected.
- Friendly-error tests: invoke wrong-context commands; assert error text matches design D3 examples.
- `--vault PATH` override tests.

---

## Hard constraints

- **Type_Safe Vault__Context.** No raw primitive fields.
- **No mocks.** Real `tmp_path`, real argparse invocations.
- **No `__init__.py` under `tests/`.**
- **Performance:** detector must be fast; cache the result within a single `sgit` invocation.
- **No behaviour change for invocations that ARE visible in their context.** Only the help / error paths change.
- Suite must pass under Phase B parallel CI shape.
- Coverage must not regress.

---

## Acceptance criteria

- [ ] `Vault__Context.detect()` works for all three contexts.
- [ ] Visibility table from design D3 fully implemented.
- [ ] Friendly errors fire for every wrong-context invocation tested.
- [ ] `sgit help all` shows the full surface.
- [ ] `--vault PATH` global override works.
- [ ] At least 9 tests (3 detector + 3 visibility + 3 friendly-error).
- [ ] Suite ≥ existing test count + N passing; coverage delta non-negative.

---

## Out of scope

- Tab-completion script generation (separate brief if needed).
- Disabled-but-shown UX variant (mentioned in design D3 §"Open"; defer).
- Detector behaviour for nested vaults (e.g., a vault inside another). Document as future-work if you encounter the case.

---

## Deliverables

1. `sgit_ai/sync/Vault__Context.py`.
2. Updates to `sgit_ai/cli/CLI__Main.py` for per-context tree construction.
3. Visibility metadata fixed on every command.
4. Test files.

---

## When done

Return a ≤ 250-word summary:
1. Detector signature + the helper(s) reused vs new.
2. Number of commands with finalised visibility metadata.
3. Friendly-error coverage (commands × contexts tested).
4. Any visibility decision that needed Architect input.
5. Test count delta + coverage delta.
