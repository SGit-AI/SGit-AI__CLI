# Brief B01 — Bug Fixes from Sonnet Debrief

**Owner:** **Villager Dev**
**Status:** Ready. Highest priority — two of these are runtime bugs.
**Estimated effort:** ~2–4 hours total
**Touches:** `sgit_ai/cli/CLI__Main.py`, `sgit_ai/workflow/{pull,fetch}/`, `sgit_ai/workflow/Workflow__Runner.py`, new `sgit_ai/safe_types/Safe_Str__Read_Key.py`, `sgit_ai/schemas/workflow/clone/Schema__Clone__State.py`, `sgit_ai/workflow/clone/Step__Clone__Derive_Keys.py`, tests.

---

## Why this brief exists

Four bugs / smells were captured in `team/villager/v0.12.x__perf-brief-pack/02__sonnet-session-update-2026-05-05.md` and the Opus mid-sprint review. None are blocking v0.13.0 (which doesn't invoke the broken paths in the default flow), but **two of them throw at runtime** if the affected code paths are exercised. Fix as a single small batch.

---

## Bugs to fix

### Bug 1 — Bug B15-1: `_fetch_missing_objects` keyword-arg mismatch

**Files:**
- `sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py` (line ~32)
- `sgit_ai/workflow/fetch/Step__Fetch__Fetch_Missing.py` (line ~32)

**Symptom:** Step calls `workspace.sync_client._fetch_missing_objects(..., on_progress=..., ...)`. Actual signature uses `_p`. Throws `TypeError: _fetch_missing_objects() got an unexpected keyword argument 'on_progress'` when invoked.

**Fix:** Change `on_progress=workspace.on_progress or (lambda *a, **k: None)` to `_p=workspace.on_progress or (lambda *a, **k: None)` in both files.

**Test:** add a functional test that invokes the step against the in-memory transfer server and asserts no TypeError. Currently the only tests are structural (step name + schema shape).

### Bug 2 — Bug B04-1: Context detection never fires at runtime

**File:** `sgit_ai/cli/CLI__Main.py`

**Symptom:** `_detect_context()` and `_cmd_wrong_context()` are defined and unit-tested, but `run()` never calls them. Wrong-context invocations (`sgit commit` outside a vault, `sgit clone` inside one) get raw errors instead of friendly hints.

**Fix:** In `run()`, before the `args.func(args)` dispatch (after `self._resolve_vault_dir(args)`, before the `try:` block):

```python
context = self._detect_context(args)
command = args.command
if command in self._INSIDE_ONLY and context.is_outside():
    self._cmd_wrong_context(command, context)
if command in self._OUTSIDE_ONLY and context.is_inside():
    self._cmd_wrong_context(command, context)
```

**Test:** add an end-to-end test that runs `CLI__Main` with an outside-context cwd and asserts the friendly-error path is taken (not the raw exception path).

### Bug 3 — Bug B19: `read_key_hex` typed as `Safe_Str__Write_Key`

**Files:**
- `sgit_ai/schemas/workflow/clone/Schema__Clone__State.py:28` — field declaration
- `sgit_ai/workflow/clone/Step__Clone__Derive_Keys.py:25` — assignment

**Symptom:** Field name says `read_key_hex` but type is `Safe_Str__Write_Key`. No `Safe_Str__Read_Key` type exists; the executor reused the closest match. Probably not a runtime bug (both are 64-hex), but a Type_Safe philosophy violation.

**Fix:**
1. Create `sgit_ai/safe_types/Safe_Str__Read_Key.py` mirroring `Safe_Str__Write_Key` (likely identical regex + length; document the distinction in the docstring).
2. Update `Schema__Clone__State.read_key_hex` to use the new type.
3. Update the assignment in `Step__Clone__Derive_Keys`.
4. Round-trip invariant test for the schema after the change.

### Bug 4 — Bug B22: `Workflow__Runner` swallows typed exceptions

**File:** `sgit_ai/workflow/Workflow__Runner.py` (line 100–123, the `except Exception:` block)

**Symptom:** Any exception inside a step is caught, captured as a string via `error_msg = str(exc)`, and re-raised as `RuntimeError(error_msg)`. Callers that try to catch typed exceptions (`Vault__Read_Only_Error`, `Vault__Clone_Mode_Corrupt_Error`, etc.) will instead see plain `RuntimeError`.

**Fix:** Preserve the original exception type when re-raising. Replace:

```python
raise RuntimeError(error_msg or 'Workflow failed')
```

with:

```python
if exc is not None:
    raise type(exc)(error_msg) from exc
raise RuntimeError(error_msg or 'Workflow failed')
```

(Capture `exc` in the `except` clause: `except Exception as exc: ...`.)

**Test:** synthetic workflow with one step that raises `ValueError('boom')`. Run via `Workflow__Runner.run()`. Assert the caller catches `ValueError`, not `RuntimeError`.

---

## Hard rules

- **No mocks.** Real fixtures, real in-memory transfer server.
- **No `__init__.py` under `tests/`.**
- **All four fixes in this brief, one or more commits.** OK to commit per fix.
- Suite must pass under `-n auto` at every commit.
- Coverage must not regress.

---

## Acceptance criteria

- [ ] All 4 bugs fixed.
- [ ] Each fix has at least one new test that would have caught the bug.
- [ ] Suite ≥ 3,068 + ~6 new tests passing.
- [ ] Coverage delta non-negative.
- [ ] `Safe_Str__Read_Key` exists and is used; `Safe_Str__Write_Key` is no longer used for read keys.
- [ ] `Workflow__Runner` test suite includes a typed-exception preservation case.
- [ ] CLI__Main wrong-context test exists.

---

## When done

Return a ≤ 200-word summary stating:
1. Each bug fix confirmed.
2. New tests added per bug.
3. Coverage + test-count delta.
