# Brief 10 — Command discovery graph + smart suggestions

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands after the vault-ops sprint (briefs 06/07/04/02/03/08/09), before visualisation. Estimated effort: ~1.5 days.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Current "command not found" UX is unhelpful in three ways:

1. **The error blob is enormous.** When the user types `sgit peek pearl-ridge-2662`, argparse dumps the entire top-level usage line plus a comma-separated list of 25 valid commands. The signal-to-noise ratio is awful. The user has to scan a wall of text to figure out their typo.

2. **No suggestions.** "Did you mean...?" doesn't exist. A user typing `peek` (intuitive — "let me peek at this vault") gets no path to discovery. The closest matches (`probe`, `info`, `inspect`) are buried in the flat list.

3. **No way to discover what sgit can do.** There's no overview that groups commands by purpose, shows context requirements (works-inside-vault vs works-anywhere), or links related commands (after `clone` you typically `commit` then `push`). Users learn sgit by trial and error.

This brief introduces:

- **(a) A friendly error formatter** that replaces argparse's default invalid-choice dump with a grouped, scannable, suggestion-aware message.
- **(b) A command graph** — a Type_Safe Schema describing every command, subcommand, and option with metadata (context requirements, common-name aliases, follow-up commands, tags). Auto-populated from argparse + a curated metadata layer. Exportable to JSON.
- **(c) Smart suggestions** — when a command isn't found, search the graph for aliases and fuzzy-matches and tell the user what they likely meant.

---

## 2. The friendly error formatter

### 2a. Subclass argparse.ArgumentParser

New file `sgit_ai/cli/CLI__Argument_Parser.py`:

```python
class CLI__Argument_Parser(argparse.ArgumentParser):
    """ArgumentParser that routes invalid-choice errors through the friendly handler."""

    def error(self, message: str):
        # Detect the "invalid choice" pattern argparse uses
        match = re.match(r"argument (\S+): invalid choice: '([^']+)' \(choose from (.+)\)", message)
        if match:
            arg_name = match.group(1)
            bad_value = match.group(2)
            valid    = [v.strip(" '") for v in match.group(3).split(',')]
            self._handle_invalid_choice(arg_name, bad_value, valid)
            sys.exit(2)
        # Fall through to default handler for everything else
        super().error(message)

    def _handle_invalid_choice(self, arg_name: str, bad_value: str, valid: list[str]):
        from sgit_ai.cli.Command__Suggester import Command__Suggester
        from sgit_ai.cli.Command__Graph     import Command__Graph

        graph     = Command__Graph().build()
        suggester = Command__Suggester(graph=graph)
        suggestions = suggester.suggest(bad_value, scope_path=self._scope_path())

        # Render
        ...  # see §2b
```

Wire this subclass into every `subparsers.add_parser(...)` call by passing `parser_class=CLI__Argument_Parser` at registration. Existing argparse calls in `CLI__Main.py` need a small refactor — set the parser_class once at the root and let it propagate via `subparsers.add_parser(...)`.

### 2b. Output format

Replace the current dump with a structured, scannable message:

```
$ sgit peek pearl-ridge-2662

  Unknown command: peek

  Did you mean:
    sgit vault info <directory>          — Display vault metadata (HEAD commit, branch list, settings)
    sgit vault probe <token>             — Check whether a vault exists on the server
    sgit inspect tree <directory>        — Walk a tree object and print its entries

  All top-level commands grouped by purpose:

    Get a vault:
      sgit clone <vault-key>              — Full clone with working copy
      sgit clone-branch <vault-key>       — Thin clone (HEAD trees only, full history)
      sgit clone-headless <vault-key>     — Credentials-only (no working copy)
      sgit clone-range <vault-key> <r>    — Specific commit range

    Create a vault:
      sgit init <vault-key>               — Initialise a new vault locally
      sgit create <vault-key>             — Initialise + push to server in one step

    Work in a vault:
      sgit status                         — Show working-copy status
      sgit commit <message>               — Commit local changes
      sgit push                           — Push to server
      sgit pull                           — Pull from server
      sgit fetch                          — Fetch without merging

  Sub-namespaces:
      sgit vault {info,probe,share,...}   — Vault lifecycle
      sgit share {send,receive,publish}   — SG/Send sharing
      sgit history {log,show,diff,...}    — Commit history
      sgit file {cat,ls,write}            — File operations
      sgit inspect {tree,object,stats}    — Read-only deep inspection
      sgit check ...                      — Health checks
      sgit dev ...                        — Debug + introspection

  Run 'sgit help <command>' for details on a specific command.
  Run 'sgit dev commands graph' to view the full command graph.
```

The grouping, descriptions, and "did you mean" come from the command graph (§3). Without the graph, the formatter falls back to the current behaviour — so the friendly formatter is robust even if the graph fails to build for any reason.

For nested errors (e.g. `sgit vault peek`), only suggest within the current namespace and its parents:

```
$ sgit vault peek pearl-ridge-2662

  Unknown command: vault peek

  Did you mean:
    sgit vault info <directory>          — Display vault metadata
    sgit vault probe <token>             — Check whether a vault exists on the server

  All sgit vault subcommands:
      info, probe, delete-on-remote, rekey, uninit, backup, backups,
      restore, clean, share, add, list, remove, show, show-key,
      remote, stash, export

  Run 'sgit vault --help' for details.
```

---

## 3. The command graph

### 3a. Schema

New file `sgit_ai/schemas/cli/Schema__Command.py`:

```python
class Schema__Command(Type_Safe):
    name             : Safe_Str__Command_Name = None    # 'clone' / 'vault info' / 'history log'
    namespace        : Safe_Str__Command_Name = None    # '' for top-level; 'vault' for subcommands
    description      : Safe_Str                = None    # one-line summary
    long_description : Safe_Str                = None    # multi-line if needed
    context          : Enum__Command_Context   = None    # NEEDS_VAULT | OUTSIDE_VAULT | UNIVERSAL
    aliases          : list[Safe_Str__Command_Name]      # ['peek', 'show'] common names users type
    tags             : list[Safe_Str__Tag]               # ['read-only', 'destructive', 'network', 'idempotent']
    follow_ups       : list[Safe_Str__Command_Name]      # ['commit', 'push'] — what typically comes next
    args             : list[Schema__Command_Arg]         # positional + optional flags
    requires_token   : bool                    = False   # SG/Send access token needed?
```

```python
class Schema__Command_Arg(Type_Safe):
    name        : Safe_Str__Arg_Name  = None
    flag        : Safe_Str__Arg_Flag  = None      # '--vault-key' for flags; '' for positionals
    is_required : bool                = False
    description : Safe_Str            = None
    default     : Safe_Str            = None
```

```python
class Schema__Command_Graph(Type_Safe):
    schema_version : Safe_UInt__Schema_Version
    commands       : list[Schema__Command]
```

Round-trip invariant required.

### 3b. Population — auto + curated

`sgit_ai/cli/Command__Graph.py`:

```python
class Command__Graph(Type_Safe):
    """Walk the argparse tree to discover commands, then layer curated metadata on top."""

    def build(self) -> Schema__Command_Graph:
        from sgit_ai.cli.CLI__Main import CLI__Main
        cli       = CLI__Main()
        parser    = cli.build_parser()
        commands  = self._walk(parser)
        commands  = self._enrich(commands)
        return Schema__Command_Graph(
            schema_version = Safe_UInt__Schema_Version(1),
            commands       = commands,
        )

    def _walk(self, parser, namespace='') -> list[Schema__Command]:
        """Recursively walk argparse subparsers to discover all commands."""
        ...
        # For each subparser action: extract name, help text, args, sub-subparsers

    def _enrich(self, commands: list) -> list:
        """Layer curated metadata (aliases, follow-ups, tags) from Command__Metadata."""
        ...
```

The `_walk` method introspects argparse's internals to extract:
- `name` from the subparser key
- `description` from the `help=` argument
- `args` by iterating each subparser's `_actions`
- nested subcommands by recursing into any `_SubParsersAction`

The `_enrich` step pulls from `Command__Metadata` — a hand-curated sidetable defined as Python data:

```python
# sgit_ai/cli/Command__Metadata.py
COMMAND_METADATA = {
    'clone': {
        'aliases'   : ['get', 'fetch-vault', 'download'],
        'tags'      : ['network', 'creates-vault', 'idempotent'],
        'context'   : Enum__Command_Context.OUTSIDE_VAULT,
        'follow_ups': ['status', 'pull', 'history log'],
    },
    'vault info': {
        'aliases'   : ['peek', 'show', 'describe'],
        'tags'      : ['read-only', 'network'],
        'context'   : Enum__Command_Context.UNIVERSAL,
        'follow_ups': ['history log', 'pull'],
    },
    'commit': {
        'aliases'   : ['save', 'snapshot'],
        'tags'      : ['local-only', 'modifies-vault'],
        'context'   : Enum__Command_Context.NEEDS_VAULT,
        'follow_ups': ['push', 'status'],
    },
    'vault move': {
        'aliases'   : ['rotate-key', 'relocate', 'move'],
        'tags'      : ['network', 'destructive', 'modifies-vault'],
        'context'   : Enum__Command_Context.NEEDS_VAULT,
        'follow_ups': ['status'],
    },
    # ... one entry per command
}
```

The metadata file is the single place where common-name aliases live. When the dev team adds a new command, they add one entry here (or the build fails — see §3c verification).

### 3c. Verification on every build

The graph build runs as part of every CLI invocation (cached after the first build per-process). If a command in argparse is missing a metadata entry, the build either:
- Logs a warning to stderr (production mode) and treats the command as having no aliases / default tags.
- Fails loudly with `RuntimeError(f'No metadata for command: {name}')` (test mode).

A test asserts every argparse-registered command has a metadata entry — so missing metadata is caught in CI, not in the field.

### 3d. JSON export

```
sgit dev commands graph              # pretty-print as a tree
sgit dev commands graph --json       # dump Schema__Command_Graph.json() to stdout
sgit dev commands graph --json -o graph.json
```

The JSON export round-trips through `Schema__Command_Graph` so external tools (visualisation, doc generators, integrations) can consume it. Useful for the future visualisation track — `sgit_show` could render this as an interactive web view of the command space.

---

## 4. Smart suggestions

### 4a. The suggester

`sgit_ai/cli/Command__Suggester.py`:

```python
class Command__Suggester(Type_Safe):
    graph : Schema__Command_Graph

    def suggest(self, bad_input: str, scope_path: str = '', max_results: int = 3) -> list[Schema__Command]:
        """Return up to max_results candidate commands ranked by relevance."""
        candidates = self._scope_filter(self.graph.commands, scope_path)

        # 1. Exact alias match — highest priority
        exact_alias_matches = [c for c in candidates if bad_input in [str(a) for a in c.aliases]]
        if exact_alias_matches:
            return exact_alias_matches[:max_results]

        # 2. Substring match against name + aliases
        substring_matches = [
            c for c in candidates
            if bad_input.lower() in str(c.name).lower()
               or any(bad_input.lower() in str(a).lower() for a in c.aliases)
        ]

        # 3. Fuzzy match (Levenshtein distance) against name + aliases
        scored = []
        for cmd in candidates:
            name_dist = self._distance(bad_input, str(cmd.name))
            alias_dist = min((self._distance(bad_input, str(a)) for a in cmd.aliases), default=99)
            best = min(name_dist, alias_dist)
            if best <= 3:                        # threshold
                scored.append((best, cmd))
        scored.sort(key=lambda x: x[0])

        # Combine, deduplicate, return top N
        seen = set()
        result = []
        for cmd in substring_matches + [c for _, c in scored]:
            if str(cmd.name) not in seen:
                seen.add(str(cmd.name))
                result.append(cmd)
        return result[:max_results]

    def _distance(self, a: str, b: str) -> int:
        """Levenshtein. Pure-Python implementation; ~50 lines, no dependency."""
        ...

    def _scope_filter(self, commands, scope_path):
        """If scope_path='vault', return only 'vault *' commands. '' returns all."""
        ...
```

`peek` → exact alias match for `vault info` → returns it. ✓

`vault peek` → exact alias within `vault` namespace → suggests `vault info`. ✓

`comit` → fuzzy match (distance 1) → suggests `commit`. ✓

`push-it` → substring match → suggests `push`. ✓

### 4b. Integration

When `CLI__Argument_Parser._handle_invalid_choice` fires, it builds the graph (cached), runs the suggester, and prints the top 3 candidates with description + usage. Falls back to the grouped command listing if no good suggestions exist (distance > 3, no aliases, no substring match).

---

## 5. New CLI surface

Three new commands under `sgit dev commands`:

```
sgit dev commands list                     # flat list of all commands with one-line descriptions
sgit dev commands graph [--json [-o FILE]] # the full graph (tree view by default)
sgit dev commands find <query>             # interactive lookup: aliases + fuzzy + substring
```

The `find` command is the user-facing tool for "what command does X?" without having to memorise everything. Example:

```
$ sgit dev commands find peek
peek matches:

  vault info <directory>            — Display vault metadata (HEAD commit, branch list, settings)
    aliases: peek, show, describe
    context: works anywhere
    tags:    read-only, network

  vault probe <token>               — Check whether a vault exists on the server
    aliases: check, ping, exists
    context: outside vault
    tags:    read-only, network
```

Useful for users learning sgit. Also surfaces commands that don't appear in the top-level help.

Plus an enhancement to `sgit help`:

```
sgit help                          # current top-level help, but reorganised by purpose
sgit help <command>                # rich help for one command (description, args, examples, follow-ups)
sgit help <topic>                  # e.g. 'sgit help cloning' → all clone-related commands grouped
```

`sgit help` doesn't replace `sgit <cmd> --help` (argparse's auto-generated help). It's an upper layer that uses the graph for richer rendering.

---

## 6. Tests

In `tests/unit/cli/`:

### 6a. Argument parser

1. `test_invalid_top_level_command_emits_friendly_error` — invoke with `peek`; assert stderr contains "Unknown command: peek" + grouped command listing + suggestion for `vault info`.
2. `test_invalid_subcommand_emits_scoped_friendly_error` — invoke with `vault peek`; assert suggestion is scoped to `vault *` commands.
3. `test_invalid_choice_with_no_close_match_falls_back_to_full_listing` — invoke with `xyzqqq`; assert no "did you mean" line, just the grouped listing.

### 6b. Command graph

4. `test_graph_round_trip` — `Schema__Command_Graph.from_json(graph.json()).json() == graph.json()`.
5. `test_graph_walk_finds_all_top_level_commands` — built graph contains every top-level command from argparse.
6. `test_graph_walk_finds_all_subcommands` — graph contains `vault info`, `vault probe`, `share send`, `history log`, etc.
7. `test_every_command_has_metadata_entry` — for each command in graph, `COMMAND_METADATA[name]` exists. **This test fails CI if a new command is added without metadata.**
8. `test_graph_export_to_json_and_reload` — export, parse, assert structural equality.

### 6c. Suggester

9. `test_exact_alias_match_returns_target_command` — `peek` → `vault info`.
10. `test_fuzzy_match_distance_threshold` — `comit` (distance 1) suggests `commit`; `xyzqqq` (distance > 3) suggests nothing.
11. `test_substring_match_works` — `push-thing` suggests `push`.
12. `test_scope_filter_respects_namespace` — `peek` in `vault` scope only suggests `vault *` commands.
13. `test_aliases_can_overlap_with_real_command_names` — alias `show` exists for `vault info`; the real command `history show` also exists; both are returned, ranked correctly.
14. `test_suggester_returns_at_most_max_results` — never returns more than 3 candidates.

### 6d. Integration / CLI

15. `test_dev_commands_graph_prints_tree` — runs the command, captures stdout, asserts structure.
16. `test_dev_commands_graph_json_export_round_trips` — `--json` output parses into the schema.
17. `test_dev_commands_find_peek_returns_vault_info` — end-to-end CLI.

---

## 7. Out of scope

- **Visual web rendering of the graph.** That's the visualisation track (`sgit_show`). This brief produces the data; visualisation consumes it. Brief 10 ships JSON export so visualisation can pick it up immediately.
- **Multi-language user-facing strings.** All error messages and descriptions in English. i18n is a future concern.
- **Auto-correction (`sgit peek` → silently runs `sgit vault info`).** No. Always require explicit confirmation; suggesting is the right balance. Auto-correct hides bugs.
- **Argument-level fuzzy matching.** If the user types `sgit clone --foobar`, argparse's existing error is fine. The friendly formatter only addresses subcommand-level errors, not flag-level errors.
- **Tab-completion via shell.** Different tooling (bash/zsh completion scripts). Future brief if the team wants it; the graph data this brief produces would be the natural input.

---

## 8. Verification checklist

When done:

- All ~17 new tests pass.
- `sgit peek pearl-ridge-2662` produces the friendly error with `vault info` as the top suggestion.
- `sgit dev commands graph --json` produces parseable JSON that round-trips through `Schema__Command_Graph`.
- `sgit dev commands find peek` returns `vault info` and `vault probe`.
- Adding a new top-level command without a metadata entry causes a CI test failure.
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~1.5 days total (parser subclass + friendly formatter ~3h, graph walker + schema ~3h, metadata seeding for current 25 commands ~2h, suggester + Levenshtein ~2h, new CLI commands ~2h, tests ~3h).
