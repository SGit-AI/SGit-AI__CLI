# Design — Context-Aware Command Visibility

**Status:** Decision captured. Implementation per brief B04.
**Owners:** Architect (design), Dev (implement).

## The principle

> The user only sees commands that make sense in their current context.
> Wrong-context commands either hide or error friendly.

## Context detection

`sgit` walks parent directories from cwd looking for `.sg_vault/`. Three results:

| Result | Context |
|---|---|
| No `.sg_vault/` found in any parent | `outside` |
| `.sg_vault/` found, working tree present | `inside-working` |
| `.sg_vault/` found, no working tree (bare) | `inside-bare` |

A fourth context is **`universal`** — commands that work in any context (often by taking an explicit `--vault PATH` argument).

Detection helper: `Vault__Context.detect(cwd)` returns one of the three. `Vault__Context.detect_with_vault_path(cwd, vault_path_arg)` accepts an explicit path override.

## Visibility per context

| Command | outside | inside-working | inside-bare | universal |
|---|:-:|:-:|:-:|:-:|
| `create`, `init`, `clone`, `clone-branch`, `clone-headless`, `clone-range` | ✓ | — | — | — |
| `status`, `add`, `commit` | — | ✓ | — | — |
| `push`, `pull`, `fetch` | — | ✓ | ✓ | — |
| `branch <…>` | — | ✓ | ✓ | — |
| `history <…>` | — | ✓ | ✓ | — |
| `file <…>` | — | ✓ | — | — |
| `vault <…>` | — | ✓ | ✓ | — |
| `inspect <…>` | — (with `--vault`) | ✓ | ✓ | ✓ |
| `dev <…>` | ✓ (some) | ✓ | ✓ | ✓ |
| `pki <…>` | ✓ | ✓ | ✓ | ✓ |
| `check <…>` | — | ✓ | ✓ | — |
| `version`, `help` | ✓ | ✓ | ✓ | ✓ |

(`✓` = visible/usable; `—` = hidden by default, errors with friendly hint if invoked.)

## Behaviour

### `sgit` (no args)

Print context-aware help — only commands visible in the current context, with a tagline:

```
$ cd /tmp/empty
$ sgit
sgit (outside any vault)

  create                    create + publish a new vault
  init                      create empty local vault
  clone <vault>             full clone
  clone-branch <vault>      thin clone (HEAD-rooted, lazy history)
  clone-headless <vault>    online-only clone
  clone-range <range>       clone a commit range
  pki <…>                   PKI key management
  dev <…>                   developer tools
  version                   show version
  help [command]            show help

  See `sgit help all` for the full command surface (including
  commands that are only visible inside a vault).
```

```
$ cd ~/projects/website
$ sgit
sgit (inside vault: website)

  status                    working-copy status
  add <path>                stage changes
  commit -m <msg>           create commit
  push                      push to remote
  pull                      pull + merge
  ...
```

### `sgit help all`

Show the FULL surface regardless of context. Useful for discoverability and documentation generation.

### Wrong-context invocation

Friendly error, not a generic "unknown command":

```
$ cd /tmp/empty
$ sgit commit -m "hi"
sgit: 'commit' is only available inside a vault.
You are not inside a vault directory.

Did you mean to:
  - create one:    sgit init   (or  sgit create)
  - clone one:     sgit clone <vault-key>
  - operate on one elsewhere:  sgit commit -m "hi" --vault PATH
```

```
$ cd ~/projects/website
$ sgit clone <key>
sgit: 'clone' is only available outside a vault.
You are inside vault: website  (~/projects/website/.sg_vault)

Did you mean to:
  - clone into a different directory:  cd .. && sgit clone <key>
  - operate on the current vault:      sgit pull   /  sgit fetch   /  sgit status
```

The error path needs the rename / context map to suggest alternatives.

### Tab completion

Auto-generated completion scripts (zsh, bash, fish) for the new argparse tree pick up context — completing only the visible commands. This is mostly free if argparse subparsers are rebuilt per context.

## Implementation sketch

```python
class Vault__Context(Type_Safe):
    state         : Enum__Vault_Context_State   # outside / inside-working / inside-bare
    vault_path    : Safe_Str__File_Path = None  # populated when inside
    vault_id      : Safe_Str__Vault_Id  = None  # populated when inside
    has_working_copy : bool

class CLI__Command_Registry(Type_Safe):
    commands : list[Schema__CLI__Command]       # one per top-level command/namespace

    def visible_in(self, context: Vault__Context) -> list[Schema__CLI__Command]:
        ...
```

Each `Schema__CLI__Command` declares its `visible_in` set as Type_Safe metadata, e.g.:

```python
Schema__CLI__Command(
    name      = 'commit',
    visible_in = [Enum__Vault_Context_State.INSIDE_WORKING],
    handler   = CLI__Vault.cmd_commit,
)
```

The argparse tree is constructed at runtime from `commands.visible_in(context)`. Wrong-context invocations come through a fallback handler that knows the full registry and emits the friendly error.

## What this design leaves open

- **`--vault PATH` global flag.** Should every command accept `--vault PATH` to override context detection? Recommendation: yes, for power users + scripts. Implementation cost is low.
- **Disabled-but-shown variant.** Some users may want to see the full tree always with disabled commands greyed out. Optional `--no-context-filter` flag on `sgit help`?
- **Performance of context detection.** Walking parents for `.sg_vault/` is fast (cached after first call within a process). Negligible cost on startup.

## Acceptance for this design

- Three-context model + universal class is agreed.
- Visibility table per command is agreed (final per-command assignment in brief B04).
- Friendly-error format is agreed.
- Implementation strategy (Type_Safe metadata + per-context argparse tree) is agreed.

Brief B04 implements.
