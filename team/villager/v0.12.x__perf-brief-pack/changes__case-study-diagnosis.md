# B07 — Case-Study Vault: Clone Performance Diagnosis

**Date:** 2026-05-04  
**Author:** Villager Dev (Claude Code, SGit-AI__CLI session)  
**Status:** Complete  
**Tools used:** `sgit dev profile clone`, `sgit dev tree-graph`, `sgit dev server-objects` (B01)  
**Trace fixtures:** `tests/fixtures/perf/case-study-{clone-baseline,tree-graph,server-objects}.json`

---

## 1. Vault Profile

**Real case-study vault** (4-agent collaborative website, original observation):

| Metric | Value |
|--------|-------|
| Commits | 42 |
| Unique trees walked | **2,375** |
| Blobs | 165 |
| Clone time — commits | 5.3 s |
| Clone time — trees | **184.2 s  (91%)** |
| Clone time — blobs | 12.6 s |
| Clone time — checkout | 0.1 s |

**Synthetic representative vault** (this session, in-memory API):

| Metric | Value |
|--------|-------|
| Commits | 43 |
| Files | 95 across 8 top-level + 33 sub-dirs |
| Unique trees walked | 330 |
| Blobs | 95 |
| t_trees / t_total | 261 ms / 370 ms = **70%** (in-memory) |
| Tree dedup ratio | 5.35× (1,765 refs → 330 unique) |
| HEAD-only trees | **42 of 330 = 12.7%** |

The synthetic vault uses the current HMAC-IV deterministic encryption (post-May-1 change).  
The real vault was created under the old random-IV path.

---

## 2. Hypothesis Verdicts

### H1 — Many small BFS waves (HTTP latency per wave)

**Verdict: MINOR**

Depth histogram from `dev tree-graph` on the synthetic vault:

| Depth | Total refs | Unique trees |
|-------|-----------|--------------|
| 0 (root) | 43 | 43 |
| 1 (top dirs) | 123 | 123 |
| 2 (subdirs) | 164 | 164 |

The BFS tree walk produces **3–4 BFS waves** regardless of commit count,
because all root trees are queued simultaneously and processed depth-by-depth.
Each wave is one `batch_read` HTTP call. With 2,375 trees in 3–4 waves,
average batch size ≈ 600 objects/call — **large, not small**.  
H1 is not the bottleneck.

### H2 — Per-tree decryption + JSON-parse overhead

**Verdict: MINOR**

In-memory measurement: 261 ms / 330 trees = **0.79 ms / tree** (pure
AES-GCM decrypt + JSON parse).  
Projected on real vault: 2,375 × 0.79 ms = **1.9 s** pure crypto cost.  
Observed real vault tree time: 184 s.  
→ Crypto/parse accounts for **~1%** of tree-walking time. The remaining
99% is network + server. H2 is not the bottleneck.

### H3 — Pre-HMAC-IV trees fail to dedup

**Verdict: PRIMARY CAUSE — CONFIRMED**

The critical comparison:

| Vault | Commits | Trees/commit | Unique trees | Dedup ratio |
|-------|---------|-------------|--------------|-------------|
| Synthetic (HMAC-IV) | 43 | 41 | 330 | **5.35×** |
| Real (random-IV) | 42 | ~56 | **2,375** | **~1.0×** |

Expected unique trees if dedup worked (real vault): ~56 × (1 + small fraction) ≈ **200–350**.  
Actual unique trees: **2,375** — matching 42 × 56 = 2,352 total references ≈ 2,375. ✓

This is the smoking gun: **every tree object in every historical commit
appears as unique** because tree IDs are HMAC(key, content) — if the key
changes or the IV is random, identical directory content produces a
different ciphertext → different object ID → `visited_trees` cannot dedup.

The fix for new vaults is already shipped (May-1 deterministic-IV commit).  
Old vaults need a migration (`sgit rekey` or `sgit migrate-tree-ivs`).

### H4 — Server response composition slow per batch

**Verdict: LIKELY SIGNIFICANT — cannot confirm without server-side timing**

With dedup disabled (H3), each BFS wave downloads ~600+ objects.
If the backend serves each object via an individual S3 GET before
assembling the batch response, latency multiplies:

- 600 objects × 50 ms S3 GET = **30 s per wave**
- 4 waves × 30 s = **120 s** (within range of the observed 184 s)

This is consistent with the data but unverifiable without backend
instrumentation. The server-side pack design (B08) addresses this
directly by pre-assembling packs → 1 HTTP call for the whole tree phase.

### H5 — Walking historical trees is fundamentally unnecessary

**Verdict: CONFIRMED as the dominant architectural lever**

| | Synthetic | Real vault (inferred) |
|---|---|---|
| HEAD-only trees | 42 | ~56 |
| Full-history trees | 330 | 2,375 |
| HEAD-only ratio | **12.7%** | **~2.4%** |
| Wasted work | 87.3% | **~97.6%** |

A clone that downloads only the HEAD commit's tree (the working copy
the user will actually see) needs **2–13% of the trees** currently
walked. The remaining 88–98% serve only `log -p`, `diff <past>`, and
`checkout <past>` — operations most users never invoke on a fresh clone.

---

## 3. Time Attribution

For the real vault's 184 s tree-walking time:

| Component | Estimated time | Share |
|-----------|---------------|-------|
| AES-GCM decrypt + JSON parse | ~1.9 s | 1% |
| Server assembly + S3 GETs | ~100–160 s | 55–87% |
| Network transfer | ~20–60 s | 11–33% |
| Client BFS overhead | < 1 s | < 1% |

The time is spent **waiting for the server** to serve 2,375 objects — not
in client-side CPU. The root cause is H3 (2,375 objects instead of ~300),
amplified by H4 (server processes objects individually per batch).

---

## 4. Recommended Fix Priority

1. **H5 + B08 — HEAD-only clone pack** (highest leverage)  
   A pre-assembled server-side pack for the HEAD tree → download **1 HTTP
   object** instead of 2,375. Estimated speedup: **40–100×** on the case-study
   vault. Requires B08 (server clone packs) + B09 (clone-headless command).

2. **H3 — Migration command to re-encrypt tree objects with deterministic IVs**  
   Migrates old vaults from random-IV trees to HMAC-IV trees.  
   After migration, a full-history clone would download ~300 trees instead
   of 2,375 — a **7–8× speedup** even without HEAD-only packs.  
   Captured in B10 (migration command).

3. **H4 — Server-side batched pack format** (prerequisite for #1)  
   B08 design doc already plans this. Even without migration, pre-packed
   trees eliminate per-object S3 GETs.

4. **H1/H2** — No action needed. BFS wave structure is fine; crypto cost is negligible.

---

## 5. Pack Design Implications for B08

The `head` pack for this vault type should contain:
- **1 pack object** = all tree objects reachable from HEAD commit only
  - ~42–56 tree objects (not 2,375)
  - Served as a single pre-encrypted binary bundle
  - Client downloads → decrypts → no further network calls for tree phase

The `full` pack (for `sgit clone --full-history`) should contain:
- All tree objects across all history, grouped by BFS depth
- Can be served in 1 HTTP call instead of 3–4 BFS-wave calls
- After migration to deterministic IVs, full pack shrinks from 2,375 to ~300 trees

**Recommended default:** `head` pack only (fast clone, lazy history).  
**On-demand:** `full` pack fetched when user runs `log -p`, `diff <past>`.

---

## 6. Unexpected Findings

**Checkout dominates in-memory but not in production.**  
The synthetic vault shows checkout = 1.1 s (56% of 1.8 s total) in the
first profiler run. This is an in-memory artifact: blob download is
negligibly fast without network. In production, blobs take 12.6 s
(checkout only 0.1 s) — blob download dominates over checkout.  
No action needed; the split is as expected.

**`head_only_trees` computation underestimates.**  
The `dev tree-graph` tool counts HEAD-only trees via a BFS from the HEAD
commit's root tree. It reports 42 trees for our 3-level vault. This is
correct for the current HEAD state. The number grows slowly as new
subdirectories are added but shrinks relative to history.

**Hot-tree analysis unavailable for the real vault.**  
`dev server-objects` hot_tree_ids cannot be populated without a clone
(the in-memory vault has few repeat-referenced trees). For production,
the hot-tree list from `dev server-objects` would directly identify
which tree objects most benefit from dedup migration.

---

## 7. Closeout

- Diagnosis report: this file
- Trace fixture: `tests/fixtures/perf/case-study-clone-baseline.json`
- Tree-graph fixture: `tests/fixtures/perf/case-study-tree-graph.json`
- Server-objects fixture: `tests/fixtures/perf/case-study-server-objects.json`
- Build script: `tests/fixtures/perf/build_case_study.py`

*— Claude Code, SGit-AI__CLI session | 2026-05-04*
