# Design D2 — Data-Source Strategy

**Status:** Architectural decision. Drives data-source design across all visualisations.

---

## The principle

A visualisation's data source can answer the question "what data do I need?" in three modes:

| Mode | Source | Cost | When |
|---|---|---|---|
| **Local** | `.sg_vault/bare/` + working tree | free | Visualisation only needs already-cloned data |
| **Remote** | Existing client API (`api.batch_read`, etc.) | network | Visualisation needs data not in the local clone (e.g., remote branch state) |
| **Cached** | A small JSON cache under `.sg_vault/local/visual_cache/` | one-time fetch | Expensive remote queries that change rarely (e.g., per-vault stats) |

Every concrete `Data_Source` declares which mode it uses. **No data-source ever writes to `bare/`** — that's the engine's territory. Visualisation data sources are read-only on the canonical store.

---

## Local data sources

### `Vault__Local__Commits`
Loads all commit objects from `bare/data/<commit-id>` reachable from refs. Returns:

```python
class Schema__Vault__Commits(Type_Safe):
    commits : list[Schema__Object_Commit]   # decrypted, in walk order
    refs    : dict[Safe_Str__Branch_Name, Safe_Str__Commit_Id]
    head    : Safe_Str__Commit_Id = None
```

### `Vault__Local__Trees`
Walks tree objects on demand. Returns:

```python
class Schema__Vault__Trees(Type_Safe):
    trees       : dict[Safe_Str__Object_Id, Schema__Object_Tree]
    by_commit   : dict[Safe_Str__Commit_Id, list[Safe_Str__Object_Id]]
    head_only   : bool                              # whether this is HEAD-only or full
```

### `Vault__Local__Stats`
Counts + sizes (no decryption needed for counts):

```python
class Schema__Vault__Stats(Type_Safe):
    total_objects     : Safe_UInt
    by_type           : dict[Safe_Str__Object_Type, Safe_UInt]
    total_size_bytes  : Safe_UInt
    largest_objects   : list[Schema__Object_Size]   # top-N
```

### `Vault__Local__Working_Tree`
Reads the materialised working copy (not the encrypted tree):

```python
class Schema__Vault__Working_Tree(Type_Safe):
    files       : list[Schema__Working_File]    # path, size, mtime
    sparse_skipped : list[Safe_Str__File_Path]  # if sparse mode
```

---

## Remote data sources (fetch-on-demand)

### `Vault__Remote__Branch_State`
Asks the server for the named branch's HEAD without pulling:

```python
class Schema__Vault__Remote_Branch(Type_Safe):
    branch_name        : Safe_Str__Branch_Name
    remote_head        : Safe_Str__Commit_Id = None
    behind             : Safe_UInt = None       # commits server has that we don't
    ahead              : Safe_UInt = None       # commits we have that server doesn't
```

### `Vault__Remote__Activity`
Aggregates activity across remote refs (commits, branches, push counts):

```python
class Schema__Vault__Remote_Activity(Type_Safe):
    pushes_last_30_days : Safe_UInt
    branches_active     : list[Schema__Branch_Activity]
    last_push_at_ms     : Safe_UInt = None
```

Note: this requires server-side metadata that may not exist today. Brief v05 (activity timeline) flags this as a "may need server endpoint" item — fall back to per-author commit counts derived from local commits if the remote endpoint isn't there.

---

## Cached data sources

For expensive analyses (e.g., walking 10,000 trees to compute dedup ratio), cache the result locally:

```
.sg_vault/local/visual_cache/
├── stats__<commit-id>.json
├── tree-graph__<commit-id>.json
└── activity__<branch>__<window>.json
```

Cache keys include the relevant commit-id so they're auto-invalidated when HEAD moves. A `Vault__Cached` data source wraps a more-expensive data source and persists/reads its output.

Cache eviction: simple — TTL of 24h, or a `--no-cache` flag to bypass. Cleanup via `sgit dev visual gc`.

---

## Mutation contract (read-only on the canonical store)

| File / dir | Visualisation may | Visualisation may NOT |
|---|---|---|
| `.sg_vault/bare/` | read | write, delete, modify |
| Working tree | read | write |
| `.sg_vault/local/` | read existing files; write only to `visual_cache/` | overwrite anything outside `visual_cache/` |
| Remote API | read via existing endpoints | call any write endpoint |

Layer-import test in v0.13.x can include a check: nothing under `sgit_show/` imports a write-side action (Push, Commit, Rekey, Init).

---

## What this design leaves open

- **Cache schema versioning** — when an analysis's output schema changes, old cached files become invalid. Add a `cache_version` field per cache-key; mismatched versions trigger re-fetch.
- **Concurrent cache writes** — multiple `sgit show <…>` invocations in parallel could race on cache writes. Use atomic write-temp + rename. Same as workspace files.
- **Remote rate-limiting** — visualisations that walk a lot of remote objects could DoS a polite client. Fix: limit fetch-on-demand to small pre-cached batches; require an explicit `--full-walk` flag for unbounded remote fetches.

---

## Acceptance for this design

- Three modes (local / remote / cached) named.
- Concrete data sources sketched per visualisation type.
- Mutation contract agreed (read-only on canonical store).
- Brief v01 implements the base classes; subsequent briefs add concrete data sources per visualisation.
