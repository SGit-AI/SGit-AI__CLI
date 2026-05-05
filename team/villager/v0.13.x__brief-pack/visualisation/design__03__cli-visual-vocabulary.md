# Design D3 — CLI Visual Vocabulary

**Status:** Style guide for CLI renderers. Drives v02–v05 brief implementations.

---

## The principle

Modern CLI is **dense, scannable, beautiful**. Use:
- **Tables** for tabular data with proper alignment.
- **Trees** for hierarchical data.
- **ASCII / unicode graphs** for DAGs + timelines.
- **Color** for status / category, with graceful degradation.
- **Truncation + ellipsis** for long strings.
- **Adaptive width** to terminal columns.

`rich` library provides all of this. Standard usage patterns below.

---

## Tables — `rich.table.Table`

For: vault stats, file lists, commit log entries, branch lists.

```python
from rich.console import Console
from rich.table import Table

table = Table(title='Vault Stats', show_lines=False)
table.add_column('Metric',     style='cyan',    no_wrap=True)
table.add_column('Value',      style='magenta', justify='right')
table.add_column('Note',       style='dim')
table.add_row('Commits',       '42',     '')
table.add_row('Unique trees',  '330',    'post-HMAC-IV dedup')
table.add_row('Blobs',         '165',    '')
table.add_row('Total size',    '4.2 MB', '')

Console().print(table)
```

Output:

```
                       Vault Stats
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric          ┃   Value ┃ Note                   ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Commits         │      42 │                        │
│ Unique trees    │     330 │ post-HMAC-IV dedup     │
│ Blobs           │     165 │                        │
│ Total size      │  4.2 MB │                        │
└─────────────────┴─────────┴────────────────────────┘
```

---

## Trees — `rich.tree.Tree`

For: directory listings, vault structure, ref hierarchies.

```python
from rich.tree import Tree
from rich.console import Console

t = Tree('vault://repo')
docs = t.add('docs')
docs.add('getting-started.md  [dim](2.1 KB)[/]')
docs.add('reference.md  [dim](14 KB)[/]')
src = t.add('src')
src.add('app.py  [dim](890 B)[/]')

Console().print(t)
```

Output:

```
vault://repo
├── docs
│   ├── getting-started.md (2.1 KB)
│   └── reference.md (14 KB)
└── src
    └── app.py (890 B)
```

---

## Commit DAG — manual ASCII art

`rich` doesn't ship a DAG primitive; build with rendered glyphs:

```
* obj-cas-imm-95b7  (HEAD, branch-clone-ca44)  add hero section
* obj-cas-imm-3a9c                              update README
*─┐ obj-cas-imm-7e21                            merge 'feature/auth' into main
│ * obj-cas-imm-bb43  (feature/auth)            implement /login
│ * obj-cas-imm-c102                            initial auth schema
*─┘ obj-cas-imm-f8a1                            initial commit
```

Glyphs:
- `*` — commit node
- `│` — vertical line (continuing parent chain)
- `*─┐ … *─┘` — merge points (branch out / back in)
- Color: HEAD ref in green, branches in cyan, dim for hashes

Build via `rich.text.Text` + manual layout. v02 implements.

---

## Activity timeline — sparkline + table

Per-day commit counts as a sparkline + a top-authors table:

```
Activity (last 30 days)
30 ┤                          ╷
   │                          │  ╷
   │      ╷       ╷           │  │  ╷
   │  ╷   │   ╷   │   ╷       │  │  │  ╷
 0 ┴──┴───┴───┴───┴───┴───┴───┴──┴──┴──┴───
   1   5   10   15   20   25   30
                                                     (days ago)

Top authors (last 30 days)
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Author           ┃  Commits  ┃ Last commit         ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ alice@team.dev   │       17  │ 2h ago              │
│ bob@team.dev     │        9  │ 3d ago              │
│ claude@anthropic │        4  │ 1d ago              │
└──────────────────┴───────────┴─────────────────────┘
```

Sparkline using unicode block characters: `▁ ▂ ▃ ▄ ▅ ▆ ▇ █`. Table per `rich.table`.

---

## Color conventions

| Use | Color |
|---|---|
| Headers / section titles | `bold cyan` |
| Numeric values (positive) | `magenta` |
| Numeric values (warning, e.g. high-churn) | `yellow` |
| Numeric values (error, e.g. failed pushes) | `red` |
| Status: ok / clean | `green` |
| Status: dirty / pending | `yellow` |
| Status: missing / failed | `red` |
| Hashes / object-ids | `dim` |
| Path / filename | (default) |
| Author names | `cyan` |
| Branch names | `bold cyan` |

`rich` supports `[color]text[/]` markup; use it sparingly.

**Graceful degradation:** when stdout isn't a tty (`os.isatty()` is False), or `NO_COLOR=1` env, or `--no-color` flag, `rich.Console(no_color=True)`. All renderers must respect this.

---

## Truncation + width

- Each renderer queries `rich.console.Console().width` and adapts.
- Long strings (paths, IDs) truncate with `…` from the middle for IDs (`obj-cas-…-95b7`) and from the right for paths (`docs/very-long-…`).
- Tables auto-shrink columns; commit-message column is the last to compress.
- `--width <N>` flag overrides terminal width (useful for CI / tests).

---

## JSON output mode

Every CLI command supports `--json`:
- Produces the analysis output schema as JSON, NOT the rendered CLI output.
- Suitable for piping into `jq`, scripting, future FastAPI consumers.
- Round-trip invariant: `Schema.from_json(cli_json_output).json() == cli_json_output`.

This is what makes the same code WebUI-ready: the JSON-renderer is the contract.

---

## Acceptance for this design

- `rich` is the chosen library.
- Color conventions agreed.
- Truncation + width strategy agreed.
- `--json` contract agreed (output is the analysis schema, not rendered text).
- v02–v05 implement renderers following these conventions.
