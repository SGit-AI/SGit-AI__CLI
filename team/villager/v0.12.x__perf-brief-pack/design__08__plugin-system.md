# Design — Plugin System

**Status:** Architecture decision captured. Implementation per brief B14.
**Owners:** Architect (loader design), Dev (implementation).

## The principle

> Every read-only namespace ships as a plugin. Plugins are
> independently versioned, separately testable, runtime-loadable,
> and feature-flaggable. Adding or removing a plugin never affects
> Crypto, Storage, Core, or Network.

## Why plugins, not just sub-namespaces

Plugins differ from CLI namespaces (`sgit inspect <…>`) in three structural ways:

| | CLI namespace | Plugin |
|---|---|---|
| Code location | `sgit_ai/cli/CLI__<Namespace>.py` | `sgit_ai/plugins/<plugin-name>/` (full sub-package) |
| Loading | Always loaded | Discovered + loaded at runtime per config |
| Test isolation | Tests in `tests/unit/cli/` | Tests in `tests/unit/plugins/<name>/` (run independently) |
| Adding/removing | Code change to `CLI__Main.py` | Drop a folder; toggle config |
| Feature flag | None (always enabled) | `enabled: true / false / experimental` |

A namespace is a CLI organising principle. A plugin is an architectural one. Both are present in v0.12: namespaces are the user-facing surface; many of those namespaces are *implemented as* plugins under the hood.

## Plugin scope

**Every read-only namespace is a plugin.** Concretely:

| Plugin | Subcommands | Source today |
|---|---|---|
| `history` | log, diff, show, blame | `Vault__Diff` (read parts), `Vault__Inspector.inspect_commit_chain` |
| `inspect` | tree, object, stats, diff-state, vault | `Vault__Inspector` |
| `file` | cat, ls (read-only — `write` stays in Core) | new + parts of `Vault__Sync` read paths |
| `check` | fsck, verify, sign-verify | new + crypto layer signature checks |
| `dev` | profile, tree-graph, server-objects, replay, workflow CLI, decrypt, encrypt, derive-keys, show-key, dump, debug, cat-object | sprawling — most splits cleanly into a plugin |
| `search` (future) | content-search, name-search | new |
| `blame` (future) | file annotation | extension of `history blame` |

Read-only operations across the new top-level surface live in plugins. State-changing operations (clone, push, pull, fetch, commit, init, branch ops, rekey, etc.) stay in **Core** as workflows.

## Plugin folder shape

```
sgit_ai/plugins/
├── __init__.py                   plugin discovery / loader
├── _base/                        base classes
│   ├── Plugin__Read_Only.py      base class for read-only plugins
│   └── Plugin__Manifest.py       Type_Safe schema for plugin metadata
│
├── history/
│   ├── __init__.py
│   ├── plugin.json               manifest (name, version, commands, deps)
│   ├── CLI__History.py           CLI parser registration
│   ├── Plugin__History.py        Plugin__Read_Only subclass
│   ├── log/
│   ├── diff/
│   ├── show/
│   ├── blame/
│   └── tests/
│
├── inspect/
│   ├── plugin.json
│   ├── ...
│
└── ...
```

Each plugin is a self-contained sub-package with its own tests.

## `Plugin__Manifest`

```python
class Schema__Plugin_Manifest(Type_Safe):
    name           : Safe_Str__Plugin_Name
    version        : Safe_Str__Semver
    sgit_min       : Safe_Str__Semver           # min sgit version this plugin supports
    sgit_max       : Safe_Str__Semver = None    # optional max (omit = forever)
    stability      : Enum__Plugin_Stability     # stable / experimental / deprecated
    commands       : list[Safe_Str__Command_Name]
    visible_in     : list[Enum__Vault_Context_State]   # per design D3
    depends_on_layers : list[Enum__Layer]       # subset of {storage, network}
```

## Plugin base class

```python
class Plugin__Read_Only(Type_Safe):
    """Base class. Subclasses register subcommands and handlers."""
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser):
        """Hook into argparse tree at the parent's subparsers slot."""
        ...

    def commands(self) -> list[Schema__CLI__Command]:
        """Return the commands this plugin provides."""
        ...
```

A future `Plugin__Read_Write` base could exist for *user-installed* extensions that mutate state — but that's out of scope for v0.12. v0.12 ships read-only plugins only.

## Discovery + loading

Discovery walks `sgit_ai/plugins/*/plugin.json` at startup, validates each manifest, applies the feature-flag config:

```json
// sgit_config.json (top-level user config) — example
{
  "plugins": {
    "history":  { "enabled": true },
    "inspect":  { "enabled": true },
    "file":     { "enabled": true },
    "check":    { "enabled": true },
    "dev":      { "enabled": true },
    "search":   { "enabled": false, "stability_required": "stable" }
  }
}
```

Disabled plugins: skipped at discovery; their commands never register; their code never imports. This is the same pattern Dinis used for ephemeral-infra backend plugins (per the v0.22 brief Dinis referenced).

If a plugin's `stability` is below the user's `stability_required` setting, it's disabled even if `enabled: true`.

## Dependency rules (per `design__06__layered-architecture.md`)

- Plugins import from **Storage** and **Network** only (read-side).
- Plugins do NOT import from Core (no calling write workflows).
- Plugins do NOT import from each other (each is independent).
- Plugins do NOT import from `cli/` (CLI calls plugins, not the reverse).

Enforced by the same import-audit test that enforces layer rules (per D6).

## Versioning + compat

- Each plugin is independently versioned (`semver` in manifest).
- A plugin's `sgit_min` / `sgit_max` constraints are checked at load.
- A plugin can be removed, replaced, or downgraded without affecting Core / Storage / Network / Crypto.
- Plugins eventually live in **separate repos** (the brief Dinis referenced makes this point); v0.12 keeps them in-tree as sub-packages, with clean separation that allows extraction later.

## CLI integration

The argparse tree is built from:
1. Top-level primitives (`clone`, `commit`, `push`, etc.) — registered by `cli/CLI__Main.py` directly.
2. Loaded plugins' `register_subparsers()` hooks.

A `sgit dev plugins list` command shows what's loaded, what's disabled, what's experimental.

## Test boundary

Plugin tests live under `tests/unit/plugins/<plugin>/`. They run as part of the full suite (`pytest tests/unit/`), but can be invoked independently for plugin development:

```
pytest tests/unit/plugins/history/         # only the history plugin
```

Per-plugin coverage is reported separately in the coverage output (per the v0.10.30 QA brief).

## Acceptance for this design

- Plugin = read-only namespace mapping confirmed.
- `sgit_ai/plugins/<name>/` sub-package shape agreed.
- `Schema__Plugin_Manifest` field set agreed.
- Loader / discovery / feature-flag flow agreed.
- Dependency rules agreed (and enforced by the same layer-import test from D6).
- v0.12 ships read-only plugins only; read-write plugin infrastructure is future work.

Brief B14 implements the loader, base classes, manifest schema, and migrates the read-only namespaces to plugin form.
