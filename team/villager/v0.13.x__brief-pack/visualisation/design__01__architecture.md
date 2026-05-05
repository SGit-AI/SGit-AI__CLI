# Design D1 — Visualisation Architecture

**Status:** Architectural decision. Drives every brief in the visualisation sub-pack.

---

## The principle

Every visualisation = three layers, separated by interface contracts:

```
┌────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Data Source   │ ──► │   Analysis   │ ──► │   Presentation   │
│                │     │              │     │                  │
│ Type_Safe      │     │ Type_Safe    │     │ Multiple         │
│ schemas in     │     │ schemas in   │     │ renderers:       │
│ from local /   │     │ + out;       │     │   CLI (rich)     │
│ remote         │     │ pure logic   │     │   JSON           │
│                │     │              │     │   HTML           │
└────────────────┘     └──────────────┘     └──────────────────┘
```

The same Analysis output goes to any renderer. The same Data Source feeds
any Analysis. **No layer knows about another layer's internals — only its
schema interface.** This is what makes the same code power CLI today and
FastAPI / WebUI later, with no rewrites.

---

## Why a separate top-level package?

- **`sgit_ai/`** is the CLI engine — must stay focused on command execution + workflow + crypto + storage.
- **`sgit_visual/`** is read-only data science on top — analytical operations, presentation, future WebUI server.

Keeping them separate means:

- The CLI engine never depends on `sgit_visual/` (no upward coupling).
- `sgit_visual/` consumes `sgit_ai/`'s public surface (workflow outputs, storage classes, schemas) like any external user.
- Future extraction to a separate pip package + repo is trivial.
- Dev iteration on visualisations doesn't risk touching mission-critical clone/push/pull paths.

Layer-import test gets one new entry: `sgit_ai.*` MUST NOT import `sgit_visual.*` (the reverse is allowed and expected).

---

## Package layout

```
sgit_visual/
├── __init__.py
├── _base/                       framework primitives
│   ├── Visualisation.py         base class
│   ├── Data_Source.py           base for data sources
│   ├── Analysis.py              base for analyses
│   ├── Renderer.py              base for renderers
│   └── Schema__Visualisation_Result.py
│
├── data_sources/                concrete data sources
│   ├── Vault__Local.py          reads bare/, refs, working tree
│   ├── Vault__Remote.py         fetch-on-demand via existing API
│   └── Vault__Cached.py         local cache wrapper
│
├── analyses/                    concrete analyses
│   ├── Commit_Graph.py          DAG construction + ordering
│   ├── Tree_Stats.py            tree counts, dedup ratios, hot trees
│   ├── Activity_Timeline.py     per-author / per-day aggregations
│   └── Tree_Browser.py          recursive tree walk for browsing
│
├── renderers/                   presentation
│   ├── _base/Renderer.py
│   ├── cli/                     CLI renderers (rich-based)
│   │   ├── Renderer__Commit_Graph__CLI.py
│   │   ├── Renderer__Tree_Browser__CLI.py
│   │   ├── Renderer__Metadata__CLI.py
│   │   └── Renderer__Activity_Timeline__CLI.py
│   ├── json/                    JSON renderers (FastAPI-ready)
│   │   ├── Renderer__Commit_Graph__JSON.py
│   │   └── ... (mirrors cli/)
│   └── html/                    HTML renderers (WebUI-ready)
│       └── ... (mirrors cli/)
│
├── visualisations/              high-level orchestrators (compose data + analysis + renderer)
│   ├── Visualisation__Commit_Graph.py
│   ├── Visualisation__Tree_Explorer.py
│   ├── Visualisation__Metadata.py
│   └── Visualisation__Activity_Timeline.py
│
└── cli/                         CLI entry points
    ├── CLI__Show.py             top-level `sgit show <…>` command
    └── ... per visualisation

tests/unit/visual/               mirrors source structure
```

---

## Base class signatures

```python
# sgit_visual/_base/Data_Source.py
class Data_Source(Type_Safe):
    """Loads + returns a Type_Safe schema. No analysis, no rendering."""
    output_schema : type = None    # Type_Safe subclass

    def load(self, **params) -> Type_Safe:
        raise NotImplementedError

# sgit_visual/_base/Analysis.py
class Analysis(Type_Safe):
    """Pure compute. Input schema in, output schema out."""
    input_schema  : type = None
    output_schema : type = None

    def analyse(self, input: Type_Safe) -> Type_Safe:
        raise NotImplementedError

# sgit_visual/_base/Renderer.py
class Renderer(Type_Safe):
    """Renders an analysis output to a target format."""
    input_schema : type = None
    format       : Enum__Render_Format = None    # CLI / JSON / HTML / PLAIN

    def render(self, input: Type_Safe) -> str | bytes | dict:
        raise NotImplementedError

# sgit_visual/_base/Visualisation.py
class Visualisation(Type_Safe):
    """High-level orchestrator. Composes a data source + analysis + renderer."""
    data_source : Data_Source = None
    analysis    : Analysis    = None
    renderer    : Renderer    = None

    def execute(self, **params) -> str | bytes | dict:
        data    = self.data_source.load(**params)
        result  = self.analysis.analyse(data)
        return self.renderer.render(result)
```

---

## FastAPI-readiness

Future FastAPI integration becomes trivial:

```python
# example future: sgit_visual_api/main.py
from fastapi import FastAPI
from sgit_visual.visualisations.Visualisation__Commit_Graph import Visualisation__Commit_Graph
from sgit_visual.renderers.json.Renderer__Commit_Graph__JSON import Renderer__Commit_Graph__JSON

app = FastAPI()

@app.get('/api/vaults/{vault_dir}/commit-graph')
def commit_graph(vault_dir: str):
    viz = Visualisation__Commit_Graph(
        data_source = Vault__Local(directory=vault_dir),
        analysis    = Commit_Graph(),
        renderer    = Renderer__Commit_Graph__JSON(),
    )
    return viz.execute()
```

The Analysis class is reused unchanged. Only the Renderer differs (JSON vs CLI).

WebUI follows the same pattern with HTML renderers.

---

## Library choice — `rich` for CLI

`rich` (https://github.com/Textualize/rich) is the recommended dependency for CLI rendering:
- Tables with auto-sizing, color, alignment.
- Trees with collapsible / expandable display.
- Syntax highlighting for code / JSON.
- Progress bars (better than what we have today).
- Gracefully degrades on dumb terminals (`NO_COLOR=1`, non-tty stdout).
- Mature, broadly used (>40k stars).

Adding `rich` adds one runtime dependency to the SGit install. Acceptable for the quality of output we want.

**Alternative considered:** stdlib + manual ANSI. Rejected — the result quality difference is huge.

---

## What this design leaves open

- **Concrete CLI invocation** — `sgit show <…>` vs `sgit visual <…>` vs `sgit explain <…>`. Decide before brief v01.
- **Whether `sgit_visual/` is a separate pip package now or later.** Recommend: in-tree for v0.13.x, extract to its own package in v0.14+ when the surface stabilises.
- **HTML renderer style** — minimal HTML for the JSON-export-equivalent, OR styled HTML ready for the WebUI? Default to minimal; let WebUI brief pick the styling.

---

## Acceptance for this design

- Three-layer model agreed.
- Package name + layout agreed (placeholder `sgit_visual/`).
- `rich` library agreed.
- Brief v01 implements the framework + first dummy visualisation; subsequent briefs add concrete visualisations.
