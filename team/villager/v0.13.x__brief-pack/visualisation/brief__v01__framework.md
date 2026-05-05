# Brief v01 — Visualisation Framework

**Owner:** **Villager Architect** (design freeze) + **Villager Dev** (implementation)
**Status:** Ready. **First brief in the visualisation sub-pack — must land before v02–v06.**
**Estimated effort:** ~2 days
**Touches:** new top-level package `sgit_visual/`, top-level `sgit show <…>` CLI command, tests under `tests/unit/visual/`.

---

## Why this brief exists

Per design D1: visualisation needs a three-layer framework (data source → analysis → renderer) that powers CLI today and FastAPI / WebUI tomorrow with no rewrites. This brief ships the framework + a first end-to-end visualisation as a smoke test (a simple `sgit show stats` that renders vault basic stats).

After this brief lands, briefs v02–v06 can run in parallel — each adds one concrete visualisation reusing the framework.

---

## Required reading

1. This brief.
2. `design__01__architecture.md` (the three-layer model).
3. `design__02__data-source-strategy.md` (data-source modes).
4. `design__03__cli-visual-vocabulary.md` (rich-library patterns + color + JSON output).

---

## Scope

### Step 1 — Confirm naming + library choice with Dinis

Open items from sub-pack `00__index.md`:
- Package: `sgit_visual` (recommended) vs `sgit_view` vs `sgit_explorer`. **Use `sgit_visual` unless Dinis overrides.**
- CLI invocation: `sgit show <…>` (recommended) vs `sgit visual <…>` vs `sgit explain <…>`. **Use `sgit show <…>`.**
- Library: `rich`. **Confirm.**

### Step 2 — Top-level package + base classes

Create `sgit_visual/` with the structure from D1 §"Package layout".

Implement base classes:
- `Visualisation`, `Data_Source`, `Analysis`, `Renderer` (per D1 signatures).
- `Schema__Visualisation_Result` — wraps any analysis output with metadata (visualisation name, timestamp, data freshness).
- `Enum__Render_Format` — CLI / JSON / HTML / PLAIN.

### Step 3 — First end-to-end visualisation: `sgit show stats`

Concrete classes:
- `Vault__Local__Stats` (data source) — counts by type from `bare/data/`, total size, top-N largest objects.
- `Stats__Summary` (analysis) — formats counts into a presentation-ready schema.
- `Renderer__Stats__CLI` — uses `rich.table.Table` per D3 conventions.
- `Renderer__Stats__JSON` — outputs the schema as JSON.
- `Visualisation__Stats` — composes data_source + analysis + renderer.
- `CLI__Show.cmd_stats(args)` — invokes the visualisation; supports `--json` + `--no-color`.

### Step 4 — Tests

- Each base class: round-trip + isolation tests.
- Concrete `Visualisation__Stats`: end-to-end against `Vault__Test_Env.setup_single_vault()`.
- CLI test: `sgit show stats <vault-dir>` returns 0; `--json` produces valid schema JSON.
- Schema round-trip on the result schema.

### Step 5 — Layer-import enforcement

Extend `tests/unit/architecture/test_Layer_Imports.py` with a test:
- Nothing under `sgit_ai/` imports `sgit_visual.*`.
- `sgit_visual/` may import `sgit_ai.*` freely (it's a downstream consumer).

### Step 6 — `pyproject.toml` updates

- Add `rich>=13.0` to dependencies.
- `sgit_visual` becomes a discoverable package (entry in `tool.setuptools.packages.find` or equivalent).
- The `sgit show` CLI gets registered through `sgit_ai/cli/CLI__Main.py` (top-level command), but the handler imports from `sgit_visual` rather than implementing inline.

---

## Hard rules

- **Type_Safe everywhere.**
- **No mocks** — real `Vault__Test_Env`, real renderer outputs (assert text contains expected substrings).
- **Layer rule:** `sgit_ai/` MUST NOT import `sgit_visual/`.
- **`--json` is the FastAPI contract** — round-trip invariant must hold.
- **`--no-color` and non-tty stdout produce uncoloured output** — no ANSI codes leaked.
- **Coverage on new code ≥ 90 %** (it's foundational).
- Suite passes under `-n auto`.

---

## Acceptance criteria

- [ ] Architect + Dinis confirmed names + library.
- [ ] `sgit_visual/` package exists with `_base/`, `data_sources/`, `analyses/`, `renderers/`, `visualisations/`, `cli/`.
- [ ] `Visualisation`, `Data_Source`, `Analysis`, `Renderer` base classes implemented.
- [ ] `Visualisation__Stats` works end-to-end with CLI + JSON renderers.
- [ ] `sgit show stats <vault-dir>` works on a real vault built via `Vault__Test_Env`.
- [ ] `--json` + `--no-color` flags work.
- [ ] Layer-import test enforces `sgit_ai/` not importing `sgit_visual/`.
- [ ] Coverage on new code ≥ 90 %.
- [ ] At least 15 new tests.

---

## When done

Return a ≤ 250-word summary:
1. Package + library + invocation names confirmed.
2. Framework files (count + LOC).
3. `sgit show stats` example output (paste a CLI render).
4. JSON output schema name + round-trip status.
5. Coverage + test count delta.
