# Brief v02 — Commit Graph Visualisation

**Owner:** **Villager Dev**
**Status:** BLOCKED until v01 lands.
**Estimated effort:** ~1 day
**Touches:** `sgit_visual/data_sources/Vault__Local__Commits.py`, `sgit_visual/analyses/Commit_Graph.py`, `sgit_visual/renderers/cli/Renderer__Commit_Graph__CLI.py`, JSON renderer, visualisation orchestrator, tests.

---

## Why this brief exists

The first real, useful visualisation: a commit DAG with merges and branches, rendered as ASCII art. Mirrors `git log --graph` but designed for SGit's two-branch (clone + named) model and richer metadata.

Per the v0.12.0 surface diagnosis: the case-study vault has 42 commits across multiple agents (alice / bob / claude / dinis). Showing the graph helps users + agents understand WHO did WHAT WHEN — the kind of thing the existing `sgit history log --oneline` doesn't quite capture.

---

## Required reading

1. This brief.
2. `design__01__architecture.md` + `design__03__cli-visual-vocabulary.md` (especially the "Commit DAG" example).
3. `sgit_ai/storage/Vault__Commit.py` and `Vault__Ref_Manager.py` — to understand commit / ref data shape.
4. The framework shipped by v01.

---

## Scope

### Data source: `Vault__Local__Commits`

Walks all commits reachable from refs. Decrypts metadata (commit message, author, parents, tree_id, timestamp, signature_present_or_not). Returns:

```python
class Schema__Vault__Commits(Type_Safe):
    commits   : list[Schema__Commit_With_Refs]
    refs      : dict[Safe_Str__Branch_Name, Safe_Str__Commit_Id]
    head      : Safe_Str__Commit_Id = None

class Schema__Commit_With_Refs(Type_Safe):
    commit_id      : Safe_Str__Commit_Id
    parents        : list[Safe_Str__Commit_Id]
    timestamp_ms   : Safe_UInt
    author         : Safe_Str__Author
    message        : Safe_Str__Commit_Message
    refs_at_commit : list[Safe_Str__Branch_Name]   # branches whose head IS this commit
    signed         : bool
```

### Analysis: `Commit_Graph`

Computes the layout: assigns each commit a "lane" (column in the ASCII graph), figures out merge points, decides display order (newest-first per-lane, topological).

Output schema:

```python
class Schema__Commit_Graph(Type_Safe):
    rows         : list[Schema__Graph_Row]
    lane_count   : Safe_UInt
    head_lane    : Safe_UInt = None

class Schema__Graph_Row(Type_Safe):
    commit_id    : Safe_Str__Commit_Id
    glyph_line   : Safe_Str__Plain_Text     # the glyphs: "*─┐ │ │"
    label        : Safe_Str__Plain_Text     # commit-id (truncated) + author + message + refs
    is_merge     : bool
    is_head      : bool
    refs_present : list[Safe_Str__Branch_Name]
```

### Renderer: `Renderer__Commit_Graph__CLI`

Per D3 vocabulary:
- `*` for commit nodes; `│` vertical; `*─┐ … *─┘` for merges.
- HEAD ref shown in green; branch names in cyan.
- Commit ids dim; messages plain; authors cyan.
- Adapts to terminal width — message column truncates first.

```
* obj-cas-imm-95b7  (HEAD, branch-clone-ca44)  alice@team        add hero section
* obj-cas-imm-3a9c                              alice@team        update README
*─┐ obj-cas-imm-7e21                            bob@team          merge feature/auth
│ * obj-cas-imm-bb43  (feature/auth)            claude@anthropic  implement /login
│ * obj-cas-imm-c102                            claude@anthropic  initial auth schema
*─┘ obj-cas-imm-f8a1                            dinis@team        initial commit
```

### Renderer: `Renderer__Commit_Graph__JSON`

Outputs `Schema__Commit_Graph.json()` — the same data, FastAPI-ready.

### Visualisation: `Visualisation__Commit_Graph`

Composes data + analysis + renderer.

### CLI: `sgit show commit-graph [--branch <name>] [--limit <N>] [--json] [--no-color]`

Default: HEAD branch; last 50 commits; coloured CLI output.

### Tests

- Synthetic vault with diamond topology (merge commit) — verify merge glyph rendering.
- Synthetic vault with linear history — verify simple linear render.
- 100-commit vault — verify `--limit` works.
- `--json` round-trips.

---

## Hard rules

- **Type_Safe** for all schemas.
- **No mocks.**
- **Adaptive width.** Renderer queries `Console.width`.
- **Color graceful degradation.** Non-tty / `NO_COLOR` produces plain text.
- Coverage non-negative.

---

## Acceptance criteria

- [ ] All four classes (data_source / analysis / cli renderer / json renderer) implemented.
- [ ] `sgit show commit-graph` works on a `Vault__Test_Env.setup_two_clones()` fixture.
- [ ] At least 8 tests including diamond + linear + limit + json.
- [ ] Output looks like the example above on a 4-author vault.
- [ ] JSON round-trip invariant holds.

---

## When done

Return a ≤ 200-word summary:
1. Tests added.
2. Sample CLI render output (paste).
3. Coverage delta.
