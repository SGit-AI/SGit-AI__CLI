# Brief v03 — Tree Explorer

**Owner:** **Villager Dev**
**Status:** BLOCKED until v01 lands.
**Estimated effort:** ~1 day
**Touches:** `sgit_show/data_sources/Vault__Local__Trees.py`, `sgit_show/analyses/Tree_Browser.py`, `Renderer__Tree_Browser__CLI.py`, JSON renderer, tests.

---

## Why this brief exists

A visual tree browser for the encrypted vault — like `tree` (the unix command) but operating on the decrypted, post-encryption-walk view of the vault, with sizes + object-ids + counts.

Useful for:
- Users who want to see what's in a vault at a glance.
- Agents that want to understand vault structure programmatically (`--json`).
- Debugging "why is this file missing from my clone?" style questions.

---

## Required reading

1. This brief.
2. `design__01__architecture.md` + `design__03__cli-visual-vocabulary.md` §"Trees".
3. `sgit_ai/storage/Vault__Sub_Tree.py` — `flatten()` method gives us the path → blob_id map.
4. The framework from v01.

---

## Scope

### Data source: `Vault__Local__Tree_View`

Given a commit-id (default HEAD), walks the tree and returns a hierarchical representation:

```python
class Schema__Tree_View(Type_Safe):
    commit_id     : Safe_Str__Commit_Id
    root          : Schema__Tree_Node
    total_files   : Safe_UInt
    total_size    : Safe_UInt    # decrypted size

class Schema__Tree_Node(Type_Safe):
    name          : Safe_Str__File_Name
    type          : Enum__Tree_Node_Type    # file / directory
    size_bytes    : Safe_UInt = None        # for files
    object_id     : Safe_Str__Object_Id = None
    children      : list[Schema__Tree_Node]   # for directories
```

### Analysis: `Tree_Browser`

Two modes:
- **Full**: returns the entire tree as `Schema__Tree_View`.
- **Path-scoped**: given a sub-path, returns just that subtree.

Adds derived stats: per-directory file count, per-directory size totals.

### CLI Renderer

Uses `rich.tree.Tree`:

```
vault://repo  (HEAD: obj-cas-imm-95b7)  165 files, 4.2 MB
├── content
│   ├── _docs (3 files, 18 KB)
│   │   ├── installation.md  (4.1 KB)
│   │   ├── quickstart.md    (6.2 KB)
│   │   └── reference.md     (8.1 KB)
│   ├── _posts (12 files, 34 KB)
│   │   └── 2026-04-30__hello-world.md  (2.8 KB)
│   └── index.md  (1.2 KB)
├── public
│   └── assets
│       ├── favicon.ico  (1.5 KB)
│       └── logo.png     (12 KB)
└── src
    ├── App.tsx     (3.4 KB)
    └── main.tsx    (920 B)
```

Color: directories `bold`, files default, sizes `dim`, totals `magenta`.

### CLI: `sgit show tree [<path>] [--commit <id>] [--depth <N>] [--ids] [--json]`

- `<path>` — optional sub-path scope (`sgit show tree content/_docs`).
- `--commit <id>` — non-HEAD commit (must already be local OR fetched lazily per design D2).
- `--depth <N>` — limit recursion.
- `--ids` — show object-ids alongside files.
- `--json` — schema output.

### Tests

- Vault with single file at root.
- Vault with deeply nested dirs (5+ levels).
- Path-scoped query (subtree).
- `--depth` limits.
- `--ids` shows object-ids.
- `--json` round-trip.

---

## Hard rules

- **Type_Safe schemas.**
- **No mocks.**
- **Lazy fetch:** if a tree object isn't local + the commit is a non-HEAD commit, the data source uses the lazy-fetch path (per design D2). This ties into B05's `fetch_tree_lazy`.
- Coverage non-negative.

---

## Acceptance criteria

- [ ] Data source / analysis / CLI / JSON renderers implemented.
- [ ] `sgit show tree` works against `Vault__Test_Env`.
- [ ] At least 6 tests.
- [ ] Output looks like the example above on a fixture vault.
- [ ] Lazy-fetch path triggers when querying non-HEAD commits.
- [ ] JSON round-trip invariant holds.

---

## When done

Return a ≤ 200-word summary:
1. Tests added.
2. Sample CLI render (paste).
3. Coverage delta.
4. Lazy-fetch behaviour confirmation.
