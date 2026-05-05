# Brief v04 — Metadata Explorer

**Owner:** **Villager Dev**
**Status:** BLOCKED until v01 lands.
**Estimated effort:** ~1 day
**Touches:** `sgit_visual/data_sources/Vault__Local__Stats.py` (extend from v01), `sgit_visual/analyses/Vault_Metadata.py`, `Renderer__Metadata__CLI.py`, JSON renderer, tests.

---

## Why this brief exists

A "vault dashboard" — counts, sizes, dedup ratios, hot trees, age, growth. The kind of thing a user or agent wants to see ONCE to understand a vault's shape. Also a debugging surface for "why is my vault so big?" / "why is dedup so poor?" questions.

Per the B07 diagnosis, the dedup ratio between commit-tree references and unique-tree-IDs is a key indicator of vault health (post-HMAC-IV). This brief surfaces it.

---

## Required reading

1. This brief.
2. `design__01__architecture.md` + `design__03__cli-visual-vocabulary.md` §"Tables".
3. `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` — for the dedup-ratio framing.
4. v01 framework (`Vault__Local__Stats` data source as starting point).

---

## Scope

### Data source: extend `Vault__Local__Stats`

Adds the following fields to its output schema:

```python
class Schema__Vault__Stats(Type_Safe):
    # existing
    total_objects     : Safe_UInt
    by_type           : dict[Safe_Str__Object_Type, Safe_UInt]
    total_size_bytes  : Safe_UInt
    largest_objects   : list[Schema__Object_Size]

    # new
    commits_total          : Safe_UInt
    trees_unique           : Safe_UInt
    trees_total_refs       : Safe_UInt   # sum of tree refs across all commits
    blobs_unique           : Safe_UInt
    dedup_ratio_trees      : Safe_Float  # trees_total_refs / trees_unique
    hot_trees              : list[Schema__Hot_Tree]   # top-N most-referenced
    oldest_commit_at       : Safe_Str__ISO_Timestamp = None
    newest_commit_at       : Safe_Str__ISO_Timestamp = None
    avg_commits_per_day    : Safe_Float = None
    by_author              : dict[Safe_Str__Author, Safe_UInt]
    sparse_mode            : bool
    bare_size_bytes        : Safe_UInt
    working_size_bytes     : Safe_UInt = None   # if working tree present

class Schema__Hot_Tree(Type_Safe):
    tree_id    : Safe_Str__Object_Id
    ref_count  : Safe_UInt
    size_bytes : Safe_UInt
```

### Analysis: `Vault_Metadata`

Aggregates the stats, derives the dedup ratio, computes "hot trees" (most-referenced top-N).

### CLI Renderer

Multi-section dashboard:

```
─ Vault: dap47prw ─────────────────────────────────────────────
  HEAD:   obj-cas-imm-95b739cf080a  (branch-clone-ca44b474e566)
  Mode:   full (working copy present)
  Size:   bare 4.2 MB · working 6.8 MB · total 11 MB

─ Counts ──────────────────────────────────────────────────────
  Commits        42      Blobs (unique)      165
  Trees (unique) 330     Tree references    1,765
  Refs           2       Keys                5

─ Dedup ───────────────────────────────────────────────────────
  Tree dedup ratio: 5.35×  ████████████░░░░  (target: ≥ 5×)
  Hot trees (most-referenced):
    obj-cas-imm-aa11   refs=42  size=1.2 KB
    obj-cas-imm-bb22   refs=38  size=890 B
    obj-cas-imm-cc33   refs=35  size=1.5 KB

─ Activity ───────────────────────────────────────────────────
  First commit:  2026-04-20  (15 days ago)
  Latest commit: 2026-05-04  (yesterday)
  Avg / day:     2.8 commits
  Top author:    alice@team.dev  (17 commits)
```

Per D3: section dividers in dim, headers in `bold cyan`, numerics in `magenta`, dedup-ratio bar in green/yellow/red based on threshold.

### CLI: `sgit show vault [--json] [--no-color]`

(Or `sgit show metadata` — choose the friendlier one. `vault` is shorter; matches the namespace pattern.)

### Tests

- Empty vault stats.
- Vault with N commits + verified dedup ratio.
- Hot-tree computation correctness.
- `--json` round-trip.
- Multi-author activity aggregation.

---

## Hard rules

- **Type_Safe** for the extended schema.
- **No mocks.**
- **Color graceful degradation.**
- Coverage non-negative.

---

## Acceptance criteria

- [ ] `Vault__Local__Stats` extended (or wrapped) with the new fields.
- [ ] `Vault_Metadata` analysis ships.
- [ ] CLI dashboard renders as in the example.
- [ ] At least 6 tests.
- [ ] `--json` round-trip invariant holds.
- [ ] Dedup ratio is computed correctly for known fixtures.

---

## When done

Return a ≤ 200-word summary:
1. Tests added.
2. Sample CLI render (paste).
3. Hot-tree algorithm verified on a fixture (top-3 by ref-count).
4. Coverage delta.
