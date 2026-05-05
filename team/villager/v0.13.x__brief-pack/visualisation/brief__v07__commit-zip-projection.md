# Brief v07 — Commit-Zip Projection Visualisation

**Owner:** **Villager Dev**
**Status:** BLOCKED until v01 lands. Best after v04 metadata-explorer (re-uses its data sources).
**Estimated effort:** ~1 day
**Touches:** `sgit_show/analyses/Commit_Zip_Projection.py`, `sgit_show/renderers/cli/Renderer__Commit_Zip_Projection__CLI.py`, JSON renderer, tests.

---

## Why this brief exists

Per `team/villager/v0.13.x__brief-pack/research__commit-zip-architecture.md` §"Visualisation-first dev approach": before implementing per-commit zip storage, build the **projection analysis** that shows what the optimisation would deliver for any given vault.

Three goals:

1. **Validate the optimisation hypothesis with real numbers** — if the projection doesn't show meaningful gains on real vaults, we know the implementation isn't worth doing.
2. **Help prioritise** — which vault shapes (deep-history? lots of small commits? infrequent large commits?) benefit most.
3. **Become the measurement tool** — after eventual implementation, re-run the projection and compare to observed numbers.

This is a **read-only analysis**. No on-disk changes, no network, no implementation of zips. Just a smart counter + renderer.

---

## Required reading

1. This brief.
2. `team/villager/v0.13.x__brief-pack/research__commit-zip-architecture.md` (the design — read in full).
3. `team/villager/v0.13.x__brief-pack/visualisation/design__01__architecture.md` + `design__03__cli-visual-vocabulary.md`.
4. `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` — the H4 server-S3-GET hypothesis this projection quantifies.
5. v04's `Vault__Local__Stats` data source (re-use where possible).

---

## Scope

### Data source: extend or wrap `Vault__Local__Commits`

For each commit in the chain, identify:
- The commit object (always 1 — it's THIS commit).
- Tree objects newly created at this commit (i.e., trees that didn't exist in any ancestor commit's reachable set).
- Blob objects newly created at this commit (same logic).

Algorithm:
1. Walk commits in topological order (oldest first).
2. Maintain a running set of "objects seen so far" across ancestors.
3. For each commit C:
   - Walk C's tree (using existing `Vault__Sub_Tree.flatten()` or similar).
   - For each object reachable from C, check: was it seen in any ancestor's reachable set?
   - If no → it's "new at C." Add to C's projected zip contents.
   - Add to running set.
4. For each commit C, record (commit_id, new_obj_count, new_obj_total_bytes).

Schema:

```python
class Schema__Commit_Zip_Projection(Type_Safe):
    vault_id            : Safe_Str__Vault_Id
    head_commit_id      : Safe_Str__Commit_Id
    commits_total       : Safe_UInt
    objects_total       : Safe_UInt          # union of all new-at-each-commit
    objects_total_bytes : Safe_UInt
    per_commit          : list[Schema__Commit_Zip_Stat]
    today_profile       : Schema__Clone_Profile        # current path
    projected_profile   : Schema__Clone_Profile        # post-zip path

class Schema__Commit_Zip_Stat(Type_Safe):
    commit_id          : Safe_Str__Commit_Id
    sequence           : Safe_UInt           # depth in chain
    new_object_count   : Safe_UInt           # commit + new trees + new blobs
    new_object_bytes   : Safe_UInt           # zip size projection
    breakdown          : Schema__Object_Breakdown   # split by type

class Schema__Clone_Profile(Type_Safe):
    http_count          : Safe_UInt           # estimated number of HTTP requests
    server_s3_gets      : Safe_UInt           # estimated server-side S3 reads
    bytes_transferred   : Safe_UInt           # total bytes
    estimated_seconds   : Safe_Float          # rough wall-clock projection
```

### Analysis: `Commit_Zip_Projection`

Computes both profiles:

**Today profile** (per the B07 diagnosis):
- HTTP count = ceil(unique-objects / 600)  ← BFS-wave size
- Server S3 GETs = unique-objects (one per object inside each batch)
- Estimated seconds: ~50ms × server S3 GETs / 8 (parallel within a wave) + per-wave network round-trip

**Projected profile** (post-commit-zip):
- HTTP count = commit-count + 2 (chain walk + zip downloads)
- Server S3 GETs = commit-count + 2 (one per zip + chain walk)
- Estimated seconds: max(commit-count / 8 × 50ms, sum-of-zip-sizes / network-bw)

Both projections are rough. The renderer makes the assumptions explicit so users understand what's projected vs measured.

### CLI Renderer

Side-by-side dashboard:

```
─ Commit-Zip Projection: vault dap47prw ──────────────────────────

  Vault profile:
    Commits: 42  ·  Total objects: 507  ·  Total size: 4.2 MB

─ Today (per-object fetch) ────────────────────────────────────────

  Estimated clone profile:
    HTTPs:           5 (BFS waves of ~100 objects each)
    Server S3 GETs:  ~507  (one per object inside batches)
    Wall-clock:      ~10–15 s  (latency + server work)

─ Projected (commit-zip fetch) ────────────────────────────────────

  Estimated clone profile:
    HTTPs:           ~44 (chain walk + 42 zips, 8 parallel)
    Server S3 GETs:  ~44  (one per zip)
    Wall-clock:      ~3–5 s  (latency-bound; one S3 GET per HTTP)

─ Per-commit zip projection ───────────────────────────────────────

  Top 5 largest commit zips (potential bottlenecks if sequential):
    obj-cas-imm-f8a1   18 objs   1.2 MB  (initial commit)
    obj-cas-imm-7e21    9 objs   142 KB  (merge commit)
    obj-cas-imm-bb43    6 objs    87 KB
    obj-cas-imm-c102    5 objs    52 KB
    obj-cas-imm-3a9c    4 objs    34 KB
  ...

─ Recommendation ──────────────────────────────────────────────────

  ✓ Commit-zip optimisation projected to deliver ~3× speedup on this vault.
  ✓ Largest zip (1.2 MB) is well under any HTTP body size limits.
  ✓ Server storage cost increase: ~4.2 MB → ~8.4 MB (acceptable).

  Recommendation: ENABLE commit-zip on next push.
```

For vaults where the projection shows minimal gain (e.g., very small vaults or already-optimal HMAC-IV vaults), the recommendation is "DEFER — current clone is already fast enough."

### CLI: `sgit show commit-zip-projection [<vault-dir>] [--json] [--no-color]`

Default: current vault. Flag for explicit dir.

### JSON Renderer

Outputs `Schema__Commit_Zip_Projection.json()` — what FastAPI/WebUI consumes.

### Tests

- Synthetic vault with 5 commits, known per-commit object counts → verify projection numbers.
- Vault with deep history (20 commits) → recommendation is ENABLE.
- Tiny vault (1 commit, 3 files) → recommendation is DEFER.
- `--json` round-trip.

---

## Hard rules

- **Type_Safe** schemas throughout.
- **No mocks** — synthetic vault via `Vault__Test_Env`.
- **Read-only.** No on-disk changes, no network calls.
- Coverage non-negative.

---

## Acceptance criteria

- [ ] `Commit_Zip_Projection` analysis ships.
- [ ] CLI dashboard renders side-by-side today vs projected.
- [ ] Recommendation logic (ENABLE / DEFER) based on projected speedup threshold.
- [ ] At least 5 tests covering small / large / merge-heavy / linear vaults.
- [ ] `--json` round-trip invariant holds.
- [ ] Output usable both standalone (CLI) and machine-readable (JSON for downstream automation).

---

## Closeout — re-run on case-study

After this brief lands, **run on the real case-study vault** (the 4-agent collaborative website Dinis demoed). Document the projection in:

`team/villager/v0.13.x__brief-pack/research__commit-zip-projection-case-study.md`

That document becomes the **decision input** for whether the commit-zip implementation brief gets prioritised in late v0.13.x or v0.14.x.

---

## When done

Return a ≤ 200-word summary:
1. Tests added.
2. Sample CLI render on a fixture vault.
3. Recommendation logic threshold (e.g., "ENABLE if projected speedup ≥ 2×").
4. Coverage delta.
5. The case-study vault projection numbers (post-closeout step).
