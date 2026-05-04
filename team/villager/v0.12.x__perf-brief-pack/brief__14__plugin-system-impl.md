# Brief B14 — Plugin System Implementation

**Owner role:** **Architect** (loader contract) + **Villager Dev** (implementation + plugin migrations)
**Status:** BLOCKED until B13 lands.
**Prerequisites:** B12 + B13 (layered restructure) merged.
**Estimated effort:** ~3–4 days
**Touches:** new `sgit_ai/plugins/` sub-tree, plugin loader, feature-flag config, migration of read-only CLI namespaces into plugins.

---

## Why this brief exists

Per `design__08__plugin-system.md` + decision: every read-only namespace ships as a plugin. After B13, the source tree has 4 layers + a CLI shim. This brief introduces the 5th layer (Plugins) and migrates all read-only namespaces into it.

---

## Required reading

1. This brief.
2. `design__08__plugin-system.md` (the architecture).
3. `design__06__layered-architecture.md` (where Plugins sit + dep rules).
4. `design__02__cli-command-surface.md` (the namespaces being converted).

---

## Scope

### Phase 1 — Loader + base classes

Create `sgit_ai/plugins/_base/`:

- `Schema__Plugin_Manifest` — Type_Safe schema (per design D8).
- `Plugin__Read_Only` — base class.
- `Schema__Plugin_Config` — user config shape.
- `Plugin__Loader` — discovery + manifest validation + feature-flag application.

Tests under `tests/unit/plugins/_base/`:
- Manifest round-trip invariant.
- Loader discovers plugins.
- Loader honours `enabled: false`.
- Loader honours `stability_required` filter.

### Phase 2 — Plugin loader integration

Wire the loader into `sgit_ai/cli/CLI__Main.py`:
- At startup, after primitive commands are registered, the loader walks `sgit_ai/plugins/*/plugin.json`.
- For each enabled plugin, call `register_subparsers()`.
- For each disabled plugin, skip (don't import).

Per-context visibility (per design D3) still applies — a plugin's `visible_in` from its manifest is consulted when the per-context argparse tree is built.

### Phase 3 — Plugin migrations (one per namespace)

For each read-only namespace, migrate to a plugin:

| Plugin | What moves |
|---|---|
| `history` | `cmd_log`, `cmd_diff`, `cmd_show`, `cmd_blame` (read parts) |
| `inspect` | `cmd_inspect_*` (the existing inspect-* family); `Vault__Inspector` moves from `objects/` (or wherever B12 left it) into `plugins/inspect/` |
| `file` | `cmd_cat`, `cmd_ls` (read paths only — `write` stays in Core) |
| `check` | `cmd_fsck`, `cmd_verify`, `cmd_sign-verify` |
| `dev` | `cmd_decrypt`, `cmd_encrypt`, `cmd_derive_keys`, `cmd_show_key`, `cmd_dump`, `cmd_debug`, `cmd_cat_object`, plus the new perf tools from B01 (profile, tree-graph, server-objects, replay), plus `dev workflow <…>` |

Per migration:
1. Create `sgit_ai/plugins/<plugin>/`.
2. Move handlers from current location into plugin folder.
3. Add `plugin.json` manifest.
4. Add `Plugin__<Plugin>(Plugin__Read_Only)` subclass with `register_subparsers()`.
5. Move tests into `tests/unit/plugins/<plugin>/`.
6. Update imports + remove old registration in `CLI__Main.py`.
7. Run full suite. Must pass.
8. Commit + push.

### Phase 4 — Feature flag config

Add `sgit_ai/config/Schema__SGit_Config.py` (or extend existing) to capture:

```python
class Schema__SGit_Config(Type_Safe):
    plugins : Schema__Plugins_Config

class Schema__Plugins_Config(Type_Safe):
    history  : Schema__Plugin_Toggle
    inspect  : Schema__Plugin_Toggle
    file     : Schema__Plugin_Toggle
    check    : Schema__Plugin_Toggle
    dev      : Schema__Plugin_Toggle
    # extensible — future plugins listed here

class Schema__Plugin_Toggle(Type_Safe):
    enabled            : bool                         = True
    stability_required : Enum__Plugin_Stability       = STABLE
```

Default behaviour with no config file: all in-tree plugins enabled, stability `stable`.

User config file lives at `~/.sgit/config.json` (top-level user config; cross-vault) and/or `<vault>/.sg_vault/local/config.json` (per-vault override).

### Phase 5 — Layer-import test extension

Extend the test from B12/B13:
- `plugins/<name>/` imports only storage, network, workflow (read-side), safe_types, schemas.
- `plugins/<name>/` does NOT import core/actions/ (no calling write workflows).
- `plugins/<name>/` does NOT import other plugins.

### Phase 6 — `sgit dev plugins` subcommands

Add to the `dev` plugin (yes, the plugin loader's dev plugin manages plugins — small bootstrap quirk):

```
sgit dev plugins list                   show loaded + disabled plugins
sgit dev plugins show <name>            show a plugin's manifest
sgit dev plugins enable <name>          enable in user config
sgit dev plugins disable <name>         disable in user config
```

### Phase 7 — Verify behaviour

After all phases:
- Full suite passes.
- Coverage delta non-negative.
- All previously-working read-only commands work under their plugin form (same CLI invocation, same output bytes).
- Disabling a plugin removes its commands from `sgit help`.
- Layer-import test passes.

---

## Hard constraints

- **Behaviour preservation per command.** Same output bytes for same inputs.
- **Type_Safe** for manifest, config, plugin base class.
- **No mocks.**
- **No `__init__.py` under `tests/`.**
- **Layer-import test stays green** at every commit.
- Coverage must not regress.
- Suite must pass under Phase B parallel CI shape.
- A plugin can be removed entirely (delete folder) without breaking the rest of the build.

---

## Acceptance criteria

- [ ] `sgit_ai/plugins/_base/` with `Plugin__Read_Only`, `Schema__Plugin_Manifest`, `Plugin__Loader`.
- [ ] All five read-only namespaces (`history`, `inspect`, `file`, `check`, `dev`) shipped as plugins under `sgit_ai/plugins/<name>/`.
- [ ] Each plugin has `plugin.json`, its own subpackage, its own tests.
- [ ] User config (`~/.sgit/config.json`) toggles plugins.
- [ ] `sgit dev plugins list / show / enable / disable` works.
- [ ] Disabling a plugin: its commands disappear from `sgit help`; its code is not imported.
- [ ] Removal-test: temporarily delete a plugin folder, suite still passes (sans that plugin's tests).
- [ ] Layer-import test extended and passing.
- [ ] Full suite ≥ 2,105 passing; coverage delta non-negative.

---

## Out of scope

- Plugins in separate repos (future work; in-tree is fine for v0.12).
- Plugin marketplace / installation flow.
- Read-write plugins (v0.12 ships read-only only).
- New plugins beyond migrations (search, blame, etc. — separate briefs later).

---

## Deliverables

1. `sgit_ai/plugins/` tree with loader + base + 5 read-only plugins.
2. Plugin config schemas + user config integration.
3. `sgit dev plugins <…>` commands.
4. Extended layer-import test.
5. Closeout note in `01__sprint-overview.md`.

---

## When done

Return a ≤ 300-word summary:
1. Plugins shipped (5 + bootstrap dev plugin).
2. Total LOC moved from `cli/` + `objects/` into `plugins/`.
3. Removal-test outcome (delete a folder, suite passes).
4. Suite + coverage deltas.
5. Anything in the loader contract that needed Architect input mid-flight.
