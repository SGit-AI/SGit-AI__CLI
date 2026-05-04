# Design — CLI Command Surface

**Status:** Decisions captured. Open inventory items called out for brief B02.
**Owners:** Architect (design), Dev (implement per briefs B02, B03).

## The principle

> Top-level = primitives only.
> Everything else lives inside an intent-grouped namespace.

A "primitive" is:
- frequent (most users hit it daily),
- self-explanatory at the top level,
- not part of a larger category.

Everything that can be grouped is. The aim: from 67 top-level commands today → ~14 + ~8 namespaces.

## Top-level tree (proposal)

```
sgit
│
├── create               init + create remote + publish (one-shot, fully published)
├── init                 create empty local vault (no remote)
├── clone                full clone (Git-compatible default)
├── clone-branch         thin clone (HEAD-rooted trees + lazy history)
├── clone-headless       online-only clone (no/cache .sg_vault)
├── clone-range          clone a commit range (PR-style)
│
├── status               working-copy status
├── add                  stage changes
├── commit               create commit
├── push                 push to remote
├── pull                 pull + merge
├── fetch                fetch without merge
│
├── version
├── help
│
├── branch <…>           list, create, switch, delete, rename
├── history <…>          log, diff, show, blame
├── file <…>             cat, ls, write
├── vault <…>            rekey, probe, delete-on-remote, info, share, wipe
├── inspect <…>          tree, stats, object, diff-state, vault (read-only inspection)
├── dev <…>              decrypt, encrypt, derive-keys, show-key, dump, debug,
│                        cat-object, profile, tree-graph, server-objects,
│                        replay, workflow <…>
├── pki <…>              keygen, sign, verify, … (already namespaced)
└── check <…>            fsck, verify, sign
```

Top-level total: **14 commands + 8 namespaces**, down from 67.

(`share` may also become its own top-level namespace if `contacts/send/receive/publish` is a distinct concern. Brief B02 inventories.)

## Namespace contents (initial categorisation)

### `branch <…>`
```
branch list                 list local + remote branches
branch create <name>
branch switch <name>        (Git's `switch`)
branch delete <name>
branch rename <old> <new>
```

### `history <…>`
```
history log [--oneline|--graph|...]
history diff [<commit>] [<commit>]
history show <commit>
history blame <file>
```

### `file <…>`
```
file cat <path>             read a file from working copy or HEAD
file ls [<path>]            list files at a path
file write <path>           write a single file (existing surgical-write)
```

### `vault <…>`
```
vault info                  vault id, branch, remote, summary
vault rekey                 rotate encryption key
vault probe <token>         probe a token type
vault delete-on-remote      destroy on server, keep local
vault share <…>             share-with-contacts ops (or moved up)
vault wipe                  destroy local
```

### `inspect <…>`  (read-only inspection — dev-flavour)
```
inspect tree                decrypted view of current tree
inspect object <id>         raw object dump
inspect stats               object store statistics
inspect diff-state          state-level diff (low-level)
inspect vault               full vault inspection (verbose)
```

### `dev <…>`  (developer / debug / perf)
```
dev decrypt                 decrypt a payload given a key
dev encrypt                 encrypt a payload given a key
dev derive-keys             derive keys from passphrase
dev show-key                display a current key
dev dump                    dump local state in detail
dev debug                   ad-hoc debug entry-point
dev cat-object <id>         decrypt + print one object
dev profile <command>       instrumented run of <command>
dev tree-graph              visualise tree DAG
dev server-objects          inventory server-side objects
dev replay <trace.json>     replay a captured trace offline
dev workflow <…>            workflow engine (sub-namespace below)
```

### `dev workflow <…>` (sub-namespace inside dev)
```
dev workflow list                  known workflows
dev workflow show <command>        list steps + schemas
dev workflow run <cmd> --step <n>  run one step
dev workflow resume <work-id>      resume an interrupted workflow
dev workflow inspect <work-id>     view workflow state + timings
dev workflow trace <command>       run full workflow with verbose per-step output
dev workflow gc                    clean up old workspaces
```

### `pki <…>`
Already namespaced; out of scope for restructure. Confirm subcommand list during brief B02 audit.

### `check <…>`
```
check fsck                  vault integrity check
check verify [<sig>]        signature / commit verification
check sign <object>         sign an object (or under pki)
```

## Top-level cruft inventory (for brief B02 to resolve)

These exist today; placement TBD:
```
add, remove, drop, wipe, clean, uninit, off, on,
update, new, pop, revert, merge-abort, stash, info,
vault, branches, remote, list, share, contacts,
send, receive, publish, keygen, fsck, check, verify, sign,
dump, debug
```

Brief B02 inventories each, decides placement (top-level / namespace / delete / merge), and produces a final canonical list before B03/B04 implement.

## Backward compatibility

**None at the command level (decision 2).** No deprecation aliases. Hard cut at v0.12.0. Users see the new surface; old script invocations error with a friendly "command moved to `<new>`" hint (the error path can know the rename map without exposing aliases).

Vault format is separately backward-compatible per decision 3.

## Context-aware visibility

See `design__03__context-aware-visibility.md`. The tree above shows the *complete* surface; what an individual `sgit help` invocation displays depends on context (inside vault, outside vault, bare).

## Exit criteria for this design

This design is "captured and ready to consume by brief B02" when:
- Top-level tree above is agreed.
- Namespace contents are agreed in principle (final assignments per command done in B02).
- Cruft inventory queue is acknowledged.
