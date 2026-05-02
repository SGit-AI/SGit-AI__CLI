# Brief B06 — Coverage Push: Direct CLI Handler Tests

**Owner role:** **Villager Dev** + **Villager QA**
**Status:** BLOCKED until B01 lands.
**Prerequisites:** B01 merged.
**Estimated effort:** ~1.5 days
**Touches:** new tests under `tests/unit/cli/`. **No source under `sgit_ai/`.**

---

## Why this brief exists

Per `design__05__coverage-roadmap.md` Path C: CLI handler methods
(`CLI__Vault.cmd_*`, `CLI__Main.cmd_*`) currently get coverage
indirectly through full CLI invocation tests. Direct handler-level
tests are:
- Faster to write (no argparse trip).
- Catch handler bugs unrelated to argument parsing.
- Cover handler error paths cleanly.

Expected delta: **+1 to +2 percentage points** (taking us from B05's
~92% to ~94%).

---

## Required reading

1. This brief.
2. `design__05__coverage-roadmap.md` Path C.
3. `team/villager/qa/v0.10.30__coverage-baseline.md` — for the per-file CLI handler coverage today.
4. `sgit_ai/cli/CLI__Vault.py` and `sgit_ai/cli/CLI__Main.py`.

---

## Scope

### Step 1 — Inventory CLI handlers

Walk `sgit_ai/cli/CLI__*.py` and list every `cmd_*` method. For each:
- Current coverage (per-line from coverage report).
- Whether it's invoked via existing CLI tests (yes / no / partial).
- Estimated complexity (LOC).

Produce: `team/villager/v0.10.30__test-framework-brief-pack/changes__cli-handler-inventory.md`.

### Step 2 — Direct handler tests

For each `cmd_*` method without direct tests:

```python
class Test_CLI__Vault__Cmd_Status:
    def test_happy_path(self):
        env = self.env  # via Vault__Test_Env or fixture
        cli = CLI__Vault(crypto=env.crypto, api=env.api)
        args = make_args(directory=env.vault_dir)
        result = cli.cmd_status(args)
        assert ...

    def test_error_path__no_vault(self):
        ...
```

Pattern:
- Use a fixture-built environment (NF1–NF5 or `Vault__Test_Env`).
- Build an `args` namespace directly (no argparse).
- Call the handler.
- Assert on the result + side effects.

### Step 3 — Helper for `args` construction

If many handlers need the same `args` shape, add a small helper at
`tests/_helpers/cli_args.py`:

```python
def make_args(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults for CLI handler tests."""
    defaults = {'directory': None, 'message': None, 'json': False, ...}
    return argparse.Namespace(**{**defaults, **kwargs})
```

This is **not a mock** — it's a real `argparse.Namespace` object built
in-test rather than via `parser.parse_args(...)`.

### Step 4 — Verify coverage delta

After each batch, re-run coverage and verify the targeted handlers
went from indirect-only coverage to direct.

---

## Hard constraints

- **No mocks.**
- **Real fixtures for vault state** (Vault__Test_Env / NF1–NF5).
- **No source change to `sgit_ai/`.**
- **Behaviour preservation** (no test should change handler semantics).
- **Suite must pass under `-n auto`.**

---

## Acceptance criteria

- [ ] Inventory doc at `changes__cli-handler-inventory.md`.
- [ ] At least 20 new direct handler tests landing (1–2 per handler).
- [ ] Overall coverage ≥ 93% (from B05's ~92%).
- [ ] CLI per-file coverage ≥ 80% (vs ~62% baseline for `CLI__Diff.py`).
- [ ] No new mocks.
- [ ] `tests/_helpers/cli_args.py` (or equivalent) shipped if used.
- [ ] Closeout note appended to `team/villager/qa/v0.10.30__coverage-baseline.md` as §I.

---

## Out of scope

- Error-path tests on non-CLI files (brief B05).
- Plugin coverage (v0.11.x B14).
- Argparse-tree tests (covered by existing CLI tests).

---

## When done

Return a ≤ 250-word summary:
1. Handlers covered (count + per-file).
2. Coverage delta overall + per-CLI-file.
3. `args` helper status (used across N handlers).
4. Anything that surfaced about a handler's design (escalate to a Dev source-change brief).
