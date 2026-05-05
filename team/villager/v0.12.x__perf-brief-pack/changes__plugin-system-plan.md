# Architect Plan — B14 Plugin System

**Produced by:** Villager Dev (B14)
**Status:** Approved — executing
**Date:** 2026-05-04
**Prerequisites:** B12 + B13 complete ✅

---

## Design decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Plugin context injection | `register_subparsers(parent_parser, context: dict)` — context carries `vault`, `diff`, `dump`, `revert`, `main` references |
| 2 | dev plugin core violations | Dev tools that clone (profile, step-clone, tree-graph, server-objects) import `core.Vault__Sync` — accepted as KNOWN_VIOLATIONS; same pattern as Vault__Transfer |
| 3 | CLI__Main fields removed | `history`, `inspect`, `file`, `check`, `dev` fields removed from CLI__Main; replaced by `Plugin__Loader` field |
| 4 | Test folder | `tests/unit/plugins/<name>/` — moved via git mv |
| 5 | config for feature flags | `~/.sgit/config.json` parsed if present; absence = all plugins enabled |

---

## Phase 1 — Plugin infrastructure (new files)

```
sgit_ai/plugins/
├── __init__.py
└── _base/
    ├── __init__.py
    ├── Schema__Plugin_Manifest.py    Type_Safe manifest
    ├── Plugin__Read_Only.py          base class with register_subparsers()
    └── Plugin__Loader.py             discovery + feature-flag + loading
```

Tests: `tests/unit/plugins/_base/`

---

## Phase 2 — 4 clean plugins (git mv)

These CLI files import only `argparse` + `Type_Safe` — no sgit_ai layer violations.

| Current path | New path |
|---|---|
| `sgit_ai/cli/CLI__History.py` | `sgit_ai/plugins/history/CLI__History.py` |
| `sgit_ai/cli/CLI__Inspect.py` | `sgit_ai/plugins/inspect/CLI__Inspect.py` |
| `sgit_ai/cli/CLI__File.py` | `sgit_ai/plugins/file/CLI__File.py` |
| `sgit_ai/cli/CLI__Check.py` | `sgit_ai/plugins/check/CLI__Check.py` |

Per plugin, also create:
- `__init__.py`
- `plugin.json` manifest
- `Plugin__<Name>(Plugin__Read_Only)` subclass

Tests moved:
| Current | New |
|---|---|
| `tests/unit/cli/test_CLI__History*` → | `tests/unit/plugins/history/` |
| `tests/unit/cli/test_CLI__Inspect*` → | `tests/unit/plugins/inspect/` |
| `tests/unit/cli/test_CLI__File*` → | `tests/unit/plugins/file/` |
| `tests/unit/cli/test_CLI__Check*` → | `tests/unit/plugins/check/` |

No test files currently exist for these 4 namespace classes — new tests added in each plugin folder.

---

## Phase 3 — dev plugin (git mv + import updates)

All `sgit_ai/cli/dev/` files move to `sgit_ai/plugins/dev/`.

| Current path | New path | Layer status |
|---|---|---|
| `cli/dev/CLI__Dev.py` | `plugins/dev/CLI__Dev.py` | Clean after import-path fix |
| `cli/dev/Dev__Profile__Clone.py` | `plugins/dev/Dev__Profile__Clone.py` | **VIOLATION**: imports `core.Vault__Sync` |
| `cli/dev/Dev__Tree__Graph.py` | `plugins/dev/Dev__Tree__Graph.py` | **VIOLATION**: imports `core.Vault__Sync` |
| `cli/dev/Dev__Server__Objects.py` | `plugins/dev/Dev__Server__Objects.py` | **VIOLATION**: imports `core.Vault__Sync` |
| `cli/dev/Dev__Step__Clone.py` | `plugins/dev/Dev__Step__Clone.py` | **VIOLATION**: imports `core.Vault__Sync` |
| `cli/dev/Dev__Replay.py` | `plugins/dev/Dev__Replay.py` | Clean after import-path fix |
| `cli/dev/Schema__*.py` (5 files) | `plugins/dev/Schema__*.py` | Clean |
| `cli/dev/workflow/CLI__Dev__Workflow.py` | `plugins/dev/workflow/CLI__Dev__Workflow.py` | Clean |
| `cli/dev/__init__.py` | `plugins/dev/__init__.py` | Replaced |
| `cli/dev/workflow/__init__.py` | `plugins/dev/workflow/__init__.py` | Replaced |

Internal import path changes (sed after git mv):
- `sgit_ai.cli.dev.*` → `sgit_ai.plugins.dev.*`

Tests moved:
- `tests/unit/cli/dev/` → `tests/unit/plugins/dev/`

---

## Phase 4 — CLI__Main wiring changes

**Imports removed:**
```python
from sgit_ai.cli.CLI__History import CLI__History
from sgit_ai.cli.CLI__Inspect import CLI__Inspect
from sgit_ai.cli.CLI__File    import CLI__File
from sgit_ai.cli.CLI__Check   import CLI__Check
from sgit_ai.cli.dev.CLI__Dev import CLI__Dev
```

**Fields removed from CLI__Main:** `history`, `inspect`, `file`, `check`, `dev`

**Field added:**
```python
from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
...
class CLI__Main(Type_Safe):
    plugin_loader : Plugin__Loader
```

**build_parser() change:**
```python
# After top-level namespace registrations (branch, remote, vault, stash, pki):
context = {
    'vault'  : self.vault,
    'diff'   : self.diff,
    'dump'   : self.dump,
    'revert' : self.revert,
    'main'   : self,
}
for plugin in self.plugin_loader.load_enabled(context):
    plugin.register_subparsers(subparsers, context)
```

**run() changes:**
- Remove `if args.command == 'dev'`, `if args.command == 'history'`, etc. guard blocks
  (namespace-level dispatch is now handled by each plugin's registered argparse handlers)
- Keep `if args.command == 'vault'` (vault is not a plugin)

**_NO_WALK_UP, _INSIDE_ONLY, _UNIVERSAL** sets: no changes needed.

---

## Phase 5 — Layer-import test extension

Add `LAYERS['plugins']` pointing to `sgit_ai/plugins/` and tests:

```python
def test_plugins_do_not_import_cli(self):
    v = self._check_layer(LAYERS['plugins'], ('sgit_ai.cli.',))
    assert v == [], 'plugins must not import cli:\n' + '\n'.join(v)

def test_plugins_do_not_import_workflow(self):
    v = self._check_layer(LAYERS['plugins'], ('sgit_ai.workflow.',))
    assert v == [], 'plugins must not import workflow:\n' + '\n'.join(v)

def test_plugins_allowed_imports(self):
    allowed = ('sgit_ai.crypto.', 'sgit_ai.storage.', 'sgit_ai.network.',
               'sgit_ai.safe_types.', 'sgit_ai.schemas.', 'sgit_ai.plugins.')
    ...
```

KNOWN_VIOLATIONS additions (4 dev tool core imports):
```python
_DEV = 'sgit_ai/plugins/dev'
KNOWN_VIOLATIONS |= {
    f'{_DEV}/Dev__Profile__Clone.py: imports sgit_ai.core.Vault__Sync',
    f'{_DEV}/Dev__Tree__Graph.py: imports sgit_ai.core.Vault__Sync',
    f'{_DEV}/Dev__Server__Objects.py: imports sgit_ai.core.Vault__Sync',
    f'{_DEV}/Dev__Step__Clone.py: imports sgit_ai.core.Vault__Sync',
}
```

---

## Phase 6 — sgit dev plugins subcommands

Added to `Plugin__Dev.register_subparsers()`:
```
sgit dev plugins list        list all plugins (enabled/disabled/stability)
sgit dev plugins show <name> show a plugin's manifest
sgit dev plugins enable <name>  write to ~/.sgit/config.json
sgit dev plugins disable <name> write to ~/.sgit/config.json
```

---

## Commit plan

| # | Commit | Scope |
|---|---|---|
| 1 | `B14: add plugin infrastructure (_base/)` | New files: Schema__Plugin_Manifest, Plugin__Read_Only, Plugin__Loader + tests |
| 2 | `B14: move history/inspect/file/check to plugins/` | git mv + Plugin wrappers + plugin.json |
| 3 | `B14: move dev namespace to plugins/dev/` | git mv + import-path sed + Plugin__Dev + plugin.json |
| 4 | `B14: wire Plugin__Loader into CLI__Main` | Remove 5 direct imports; add loader; pass context |
| 5 | `B14: extend layer-import test for plugins layer` | LAYERS['plugins'] + 3 new tests + 4 KNOWN_VIOLATIONS |
| 6 | `B14: add sgit dev plugins subcommands` | list/show/enable/disable |
| 7 | `B02: add closeout note to sprint overview` | Documentation only |

---

## Risk notes

- **context injection**: The `context` dict approach is duck-typed (not Type_Safe). This is intentional — the context is internal CLI plumbing, not a user-facing schema.
- **dev KNOWN_VIOLATIONS**: 4 violations accepted. Fix path: extract a thin `read_vault()` / `clone_to_temp()` helper into network layer; dev tools call that. Deferred to a future brief.
- **`dev __init__.py` in tests**: `tests/unit/cli/dev/` has no `__init__.py` (project rule). Same for `tests/unit/plugins/dev/`.
- **`_sg_vault_dir`, `_bfs_commits`, `_bfs_trees_with_depth`** are module-level functions in Dev__Tree__Graph.py — pre-existing CLAUDE.md violation; not fixed in B14 (tracked separately).
