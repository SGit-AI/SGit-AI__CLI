# Finding 03 — `cli/__init__.py` Purity and CLI__* Class Pattern

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** info (compliance is intact)
**Owners:** —

---

## Result

**PASS** — `sgit_ai/cli/__init__.py` is 7 lines, contains zero command
logic, and is unchanged in this sprint. All 8 new commands added in
v0.10.30 (probe, write, fetch, cat, ls, delete-on-remote, rekey wizard,
rekey check/wipe/init/commit, clean) live in `CLI__Vault.py` as
`cmd_*` methods on the `CLI__Vault(Type_Safe)` class.

## Evidence

`sgit_ai/cli/__init__.py` (full content, 7 lines):

```python
from sgit_ai.cli.CLI__Main        import CLI__Main
from sgit_ai.cli.CLI__Vault       import CLI__Vault
from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store


def main():
    CLI__Main().run()
```

CLAUDE.md §7 ("No code in `cli/__init__.py`") is satisfied:

- Three imports (allowed).
- Single `main()` entry point that delegates to `CLI__Main().run()`
  (allowed).
- No `if __name__ == '__main__'` block, no argument parsing, no
  command dispatch.

## New commands and their location

| Command | Method | File | Line |
|---------|--------|------|-----:|
| `sgit probe` | `cmd_probe` | `CLI__Vault.py` | 928 |
| `sgit delete-on-remote` | `cmd_delete_on_remote` | `CLI__Vault.py` | 956 |
| `sgit rekey` | `cmd_rekey` | `CLI__Vault.py` | 989 |
| `sgit rekey check` | `cmd_rekey_check` | `CLI__Vault.py` | 1076 |
| `sgit rekey wipe` | `cmd_rekey_wipe` | `CLI__Vault.py` | 1097 |
| `sgit rekey init` | `cmd_rekey_init` | `CLI__Vault.py` | 1116 |
| `sgit rekey commit` | `cmd_rekey_commit` | `CLI__Vault.py` | 1137 |
| `sgit ls` | `cmd_ls` | `CLI__Vault.py` | 1232 |
| `sgit fetch` | `cmd_fetch` | `CLI__Vault.py` | 1267 |
| `sgit cat` | `cmd_cat` | `CLI__Vault.py` | 1295 |
| `sgit write` | `cmd_write` | `CLI__Vault.py` | 1328 |

All 11 new methods are on `CLI__Vault(Type_Safe)`, using the existing
`cmd_*` naming convention. No new top-level functions, no new
`@staticmethod`, no command logic in `__init__.py`.

## Side observation (referenced from finding 06)

`CLI__Vault.py` is now **1381 LOC** with 47 `cmd_*` methods. The
class-pattern compliance is fine, but the file size has grown
considerably this sprint. Architect-only concern (file split is a
boundary decision, not a Villager Dev one).

## Suggested next-action

None on this finding — compliance is intact. Linked to finding 06
for the file-size flag.
