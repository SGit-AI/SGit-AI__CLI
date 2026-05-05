# Brief v06 — WebUI Export Preparation

**Owner:** **Villager Architect** (contract review) + **Villager Dev** (implementation)
**Status:** BLOCKED until v02–v05 land (consumes their JSON output schemas).
**Estimated effort:** ~½ day
**Touches:** new `sgit_visual/exports/` sub-package, contract tests, no CLI changes.

---

## Why this brief exists

The whole point of the visualisation architecture (per D1) is that **the same code powers CLI today AND FastAPI / WebUI later** — with no rewrites. v02–v05 each ship a `Renderer__<X>__JSON` that returns the analysis schema as JSON.

This brief locks the **export contracts** down: a top-level package + manifest that lists every visualisation, its input parameters, its output schema. The future FastAPI / WebUI work consumes this manifest directly — auto-generating endpoints + UI cards.

No new visualisations. No CLI changes. Just the contract layer.

---

## Required reading

1. This brief.
2. `design__01__architecture.md` §"FastAPI-readiness".
3. The four visualisations from v02–v05.
4. The framework from v01.

---

## Scope

### `Schema__Visualisation_Manifest`

Type_Safe schema describing every available visualisation:

```python
class Schema__Visualisation_Manifest(Type_Safe):
    name            : Safe_Str__Visualisation_Name
    description     : Safe_Str__Description
    input_params    : list[Schema__Param_Definition]   # what FastAPI/WebUI must collect
    output_schema   : Safe_Str__Schema_Class_Name      # the schema class returned by JSON renderer
    cli_command     : Safe_Str__Plain_Text             # e.g. "sgit show commit-graph"
    needs_vault     : bool = True                      # does it operate on a specific vault?
    estimated_cost  : Enum__Cost_Estimate = LIGHT      # LIGHT | MEDIUM | HEAVY (drives WebUI loading UI)

class Schema__Param_Definition(Type_Safe):
    name        : Safe_Str__Param_Name
    type        : Enum__Param_Type     # string | int | bool | enum
    required    : bool = False
    default     : Safe_Str__Plain_Text = None
    description : Safe_Str__Description = None
```

### `Visualisation__Registry`

Auto-discovers all `Visualisation` subclasses in `sgit_visual/visualisations/` (mirrors `Workflow__Registry` from B08). Exposes:

```python
class Visualisation__Registry(Type_Safe):
    def list_all(self) -> list[Schema__Visualisation_Manifest]: ...
    def get(self, name) -> type[Visualisation]: ...
    def execute(self, name, params: dict) -> dict:
        """Convenience: instantiate viz with JSON renderer + execute."""
```

### Manifest publishing

Each `Visualisation__<X>` class declares its manifest as a class attribute:

```python
class Visualisation__Commit_Graph(Visualisation):
    manifest = Schema__Visualisation_Manifest(
        name        = 'commit-graph',
        description = 'Commit DAG with merges and branches',
        input_params = [
            Schema__Param_Definition(name='branch', type='string', required=False),
            Schema__Param_Definition(name='limit',  type='int',    required=False, default='50'),
        ],
        output_schema  = 'Schema__Commit_Graph',
        cli_command    = 'sgit show commit-graph',
        needs_vault    = True,
        estimated_cost = COST.LIGHT,
    )
    # ... rest
```

### CLI: `sgit show list` (or `sgit dev visualisations list`)

Prints the manifest:

```
Visualisations available:
  stats          Vault counts + sizes (sgit show stats)              ★
  commit-graph   Commit DAG with merges + branches (sgit show commit-graph)  ★
  tree           Tree explorer (sgit show tree)                      ★
  vault          Vault metadata dashboard (sgit show vault)          ★★
  activity       Per-author / per-day commit activity (sgit show activity) ★

★ = LIGHT, ★★ = MEDIUM, ★★★ = HEAVY
```

`--json` produces the full manifest list — what FastAPI consumes.

### Contract tests

For every visualisation:
- Manifest is well-formed (Type_Safe validates).
- `output_schema` string resolves to an actual Type_Safe class.
- Invocation via `Visualisation__Registry.execute(name, params)` produces JSON that `Schema.from_json(...)` round-trips successfully.
- Manifest's `cli_command` matches the actual registered CLI command.

### Future FastAPI integration sketch (NOT implemented in this brief)

Worth documenting at the bottom of the brief — make the path explicit:

```python
# future: sgit_visual_api/main.py
from fastapi import FastAPI
from sgit_visual._base.Visualisation__Registry import Visualisation__Registry

app = FastAPI()
registry = Visualisation__Registry()

@app.get('/visualisations')
def list_visualisations():
    return [m.json() for m in registry.list_all()]

@app.post('/visualisations/{name}/execute')
def execute(name: str, params: dict):
    return registry.execute(name, params)
```

The WebUI similarly: render a list of manifest cards, on click fetch `/visualisations/<name>/execute` and render the schema-typed JSON.

---

## Hard rules

- **Type_Safe** for the manifest + registry.
- **No new visualisations** — this brief is contract-only.
- **No FastAPI dependency added.** This brief just preps the contracts.
- **Backward compat:** if a future visualisation (v0.14+) lands without a manifest, the registry should warn but not break.

---

## Acceptance criteria

- [ ] `Schema__Visualisation_Manifest` + `Visualisation__Registry` exist.
- [ ] All five v01–v05 visualisations have a manifest.
- [ ] Contract tests for each (manifest validity + output_schema resolves + round-trip).
- [ ] `sgit show list` prints the manifest table.
- [ ] FastAPI integration sketch documented in the v0.14 backlog (an addendum doc OK).

---

## When done

Return a ≤ 200-word summary:
1. Manifest schema + registry shipped.
2. All 5 visualisations have manifests.
3. Contract tests added (count).
4. Coverage delta.
5. Sample `sgit show list` output (paste).
