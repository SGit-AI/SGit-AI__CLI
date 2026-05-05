# v0.12.x Mid-Sprint Review (Opus deep audit)

**Date:** 2026-05-04
**Author:** Villager orchestrator (Opus review pass)
**Scope:** Code review + brief mapping for the v0.12.x perf brief-pack
implementation by the two Sonnet sessions. **Mission-critical code audit.**

---

## Headline status

| Metric | Pre-sprint (v0.12.0) | Now |
|---|---:|---:|
| Tests collected | 2,748 | **3,005** (+257) |
| Top-level CLI commands | ~70 | **22** (−69%) |
| Source layer enforcement | None | **18-test layer-import suite passes** |
| Briefs landed (B01–B15) | 0 / 15 | **9 / 15** |

**Strong sprint.** 9 of 15 briefs done in ~2 days through 10 documented
merges. The Architect plan held; the case-study diagnosis confirmed our
H3 + H5 hypotheses; the layered restructure shipped without breaking the
suite. Below: per-brief status, code findings, gaps, and recommended
next moves.

---

## 1. Per-brief status

| # | Brief | Status | Notes |
|---|---|---|---|
| B01 | Instrumentation tools | ✅ Complete | 5 tools shipped under `sgit dev <…>` (profile, tree-graph, server-objects, step-clone, replay) |
| B02 | CLI namespaces | ✅ Complete | 70 → 22 top-level; new namespaces `branch/history/file/inspect/check/dev`. Some long-tail (`stash`, `remote`, `send`, `receive`, `publish`, `export`) still top-level — see gap §3.5 |
| B03 | clone family + `create` | ✅ Complete | `create` + 3 clone-family stubs + `--bare` flag |
| B04 | Context-aware visibility | ✅ Complete | `Vault__Context` detector + `--vault` override + `sgit help all` |
| B05 | Workflow framework | ✅ Complete | `Step` / `Workflow` / `Workflow__Workspace` / `Workflow__Runner` + `sgit dev workflow <…>` CLI |
| B06 | Apply workflow to clone | ⚠️ **Partial** — see §2.3 | Only `_clone_with_keys` workflow-driven; `clone_read_only`, `clone_from_transfer`, simple-token paths are NOT |
| B07 | Diagnose case-study | ✅ Complete | High-quality diagnosis; H3 + H5 confirmed as primary causes |
| B08 | Server clone packs | ⏳ Not started | Highest-leverage fix per B07 (40–100× speedup expected) |
| B09 | Per-mode clone impl | ⏳ Not started — stubs only | Real impls for clone-branch/headless/range still pending |
| B10 | Migration command | ⏳ Not started | **Critical for old vaults** — B07 confirmed they can't dedup without re-keying tree IVs |
| B12 | Storage layer extract | ✅ Complete | `sgit_ai/storage/` with 6 files; layer-import test enforces |
| B13 | Core + Network split | ✅ Complete | `sync/` deleted; 12 sub-classes in `core/actions/<command>/`; `api/` + `transfer/` under `network/`; `pki/` under `crypto/` |
| B14 | Plugin system | ⏳ Not started | Read-only namespaces still hard-coded in `cli/` |
| B15 | Push/pull/fetch generalize | ⏳ Not started | Awaits B06 full coverage and B08 server packs |
| B23 | E3+E4 (Graph_Walk + batch_download) | ⏳ Not started | Updated B06 said to fold E3 in; was NOT done — see gap §3.1 |

---

## 2. Code findings (Opus deep review)

### 2.1 Layer-import test is solid; 7 known violations are real debt

`tests/unit/architecture/test_Layer_Imports.py` (229 lines, 18 tests, all passing) enforces the dep graph. Two tracked violations:

**Violation A — `sgit_ai/crypto/Vault__Crypto.py` imports `Simple_Token` from `network`.** Inline imports inside two methods (lines 100, 111). This is a real architectural smell: crypto should depend on nothing per design D6. The fix: `Simple_Token` either moves into crypto (it's mostly token-derivation logic) OR gets a thin crypto-only wrapper. **Track in a follow-up brief — this is not just a comment, it's a layer-rule violation that's being amnestied.**

**Violation B — `sgit_ai/network/transfer/Vault__Transfer.py` imports 6 storage classes.** The whole file (320 LOC) is mis-located. Per the test's comment: "Vault__Transfer mixes network + storage concerns; it should move to core/." A moderate refactor — move file to `sgit_ai/core/actions/transfer/` and update CLI handlers. **Concrete brief candidate.**

### 2.2 Workflow framework: solid foundation, three concerns

The runner (`sgit_ai/workflow/Workflow__Runner.py`) handles **idempotency** (line 74: `if step.is_done(ws): continue`), **resume** (workspace persistence), **version-check** (refuses cross-major resume, line 32–37), **manifest tracking** (4 writes per step), **transaction-log emission** (off by default per D7), and **cleanup** (success + `keep_work` flag). All design D4 properties present.

**Three concerns worth flagging:**

1. **Single-state pattern instead of typed I/O per step.** Every clone step has `input_schema = output_schema = Schema__Clone__State`. Each step takes the full state and returns an enriched copy. This is a deviation from design D4's per-step-typed-I/O model. Pros: simple. Cons: weaker compile-time safety; a step could accidentally depend on a field no prior step set; the JSON round-trip per step (`data = input.json(); data['x'] = y; return Schema__Clone__State.from_json(data)`) has cumulative perf cost across 10 steps.

2. **Generic `RuntimeError` swallows typed exceptions.** `Workflow__Runner.run()` catches `Exception`, stores `error_msg = str(exc)`, and re-raises `RuntimeError(error_msg or 'Workflow failed')` (line 123). If a step raises `Vault__Read_Only_Error` or `Vault__Clone_Mode_Corrupt_Error` (typed exceptions from B13 of v0.10.30), callers now see plain `RuntimeError` instead. Likely a behaviour regression vs the original `_clone_with_keys` for some edge cases. **Verify with a test that the typed exceptions still propagate, or wrap with `raise type(exc)(...) from exc`.**

3. **Manifest write per step status transition (PENDING → RUNNING → COMPLETED) = 3+ disk writes per step.** For 10 clone steps that's 30+ writes during a clone — small but non-trivial. Could batch on completion + on failure.

### 2.3 ⚠️ B06 only refactored the **full-clone** path

`sgit_ai/core/actions/clone/Vault__Sync__Clone.py` has **four clone implementations**:

| Method | Workflow-driven? |
|---|:-:|
| `_clone_with_keys` (full clone) | ✅ Yes — uses `Workflow__Clone` |
| `clone_read_only` (Brief 05's `--read-key`) | ❌ No — parallel implementation, lines 80–264 |
| `clone_from_transfer` (transfer/SG-Send flow) | ❌ No — parallel implementation, lines 266+ |
| `_clone_resolve_simple_token` (share-token branch) | ❌ No — internal helper |

**The `clone_read_only` path is ~180 lines of duplicated clone logic** that doesn't go through any Step / Workflow. This means:
- Any improvement made to the workflow steps (e.g., when B08 server packs land) does NOT improve read-only clones.
- `sgit dev step-clone <vault-key> <dir>` (which exercises the workflow) misses the read-only path entirely — diagnostic gap.
- Type_Safe state schema benefits don't apply to the parallel paths.

**This is the single largest gap in the sprint.** B06's intent was "clone is workflow-driven"; reality is "the simplest clone path is workflow-driven." Brief 06 should be re-opened or a follow-up brief should fold `clone_read_only` and `clone_from_transfer` into `Workflow__Clone` (likely as variant entry-points or per-mode steps).

### 2.4 🐛 Type-safety smell: `read_key_hex` typed as `Safe_Str__Write_Key`

In `sgit_ai/schemas/workflow/clone/Schema__Clone__State.py:28`:

```python
read_key_hex          : Safe_Str__Write_Key   = None
```

And in `Step__Clone__Derive_Keys.py:25`:

```python
read_key_hex          = Safe_Str__Write_Key(keys['read_key']),
```

The field NAME says `read_key`, the TYPE says `write_key`. They're different keys with different semantics (read_key for decryption; write_key for upload authorization). No `Safe_Str__Read_Key` type exists in `sgit_ai/safe_types/` — the executor reused the closest available.

**Probably not a runtime bug** (both keys are 64-character hex; the regex/length validators on `Safe_Str__Write_Key` accept the read_key value). **Definitely a Type_Safe philosophy violation** — distinct domain concepts deserve distinct types. Easy fix: create `Safe_Str__Read_Key`, update the two sites.

### 2.5 B07 diagnosis is excellent

`team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` (180 lines) confirms our hypotheses with numbers:

- **H3 (random-IV trees fail to dedup) = primary cause.** Real vault has 2,375 unique tree-IDs ≈ 42 commits × 56 trees/commit (no dedup). Synthetic vault under HMAC-IV has 5.35× dedup, dropping unique trees from 1,765 refs → 330 actual.
- **H5 (historical-tree walk is mostly wasted) = dominant architectural lever.** 87.3–97.6% of walked trees are NOT needed for the HEAD working copy.
- **H1 (small BFS waves) = NOT the bottleneck** — only 3–4 waves regardless of vault size.
- **H2 (per-tree decrypt overhead) = NOT the bottleneck** — 0.79 ms/tree × 2,375 = ~1.9s, only 1% of the 184s.
- **H4 (server response composition) = LIKELY significant** — 600 objects × 50ms S3 GET ≈ 30s/wave × 4 waves ≈ 120s, consistent with observed 184s. Cannot confirm without server-side instrumentation.

**Recommended fix priority (per the diagnosis doc):**
1. **B08 — HEAD-only clone pack** (40–100× speedup expected on case-study).
2. **B10 — Migration command** for old random-IV vaults (7–8× speedup even without packs).
3. **H4 — server-side batched pack format** (already in B08 design).

This is exactly what the original strategy doc anticipated. **B08 + B10 are now the highest-leverage remaining work in the sprint.**

### 2.6 Test layout drift: tests didn't move with source

Source went `sgit_ai/sync/Vault__Sync.py` → `sgit_ai/core/actions/<command>/Vault__Sync__<X>.py`. Tests stayed at `tests/unit/sync/test_Vault__Sync__*.py` (96 files). Suite still passes; tests just aren't co-located with their source.

**Not blocking, but worth flagging:** future contributors looking for the test of `sgit_ai/core/actions/clone/Vault__Sync__Clone.py` won't find it under `tests/unit/core/actions/clone/`. Cosmetic; low priority for now. A small "test-layout mirror" brief later would fix it.

### 2.7 B23 (E3 + E4) NOT folded into B06 despite the updated brief

The updated B06 explicitly recommended folding Brief 23's E3 (`Vault__Graph_Walk`) into the `walk_trees` step. The executor implemented `Step__Clone__Walk_Trees.py` with the BFS inline (lines 25–47) instead of extracting `Vault__Graph_Walk`. Result: the BFS code is still duplicated between the workflow step and `_fetch_missing_objects` (in `core/actions/pull/`). **B23 work is fully outstanding.**

E4 (`batch_download` on `Vault__Object_Store`) — also not done. No method by that name exists in the storage layer.

### 2.8 Top-level CLI cruft remains

22 top-level commands is great vs 70, but **6 long-tail commands are still at top level** when the design said they should namespace:

| Top-level | Original brief intent |
|---|---|
| `stash` | Could go under `vault stash <…>` or stay (used frequently?) |
| `remote` | Could go under `vault remote <…>` |
| `send`, `receive`, `publish` | Brief B02 flagged these as a possible `share <…>` namespace |
| `export` | Could go under `vault export` or stay |

The executor likely deferred these because they need product-level decisions (where does `share` go?). Worth resolving in a small follow-up.

---

## 3. Gaps in the phases delivered

### 3.1 B23 (E3 + E4 carry-forward) — **outstanding**
Recommendation: ship as a small standalone brief (1–1.5 days). The BFS and blob-bucketing code already duplicated across clone + pull is a real maintenance hazard once B08 packs land — a packed clone shouldn't have to maintain TWO different BFS callers.

### 3.2 B06 — **partial coverage** (only full-clone)
Recommendation: a B06b follow-up brief to fold `clone_read_only` and `clone_from_transfer` into `Workflow__Clone` (likely as alternate entry points or per-mode variants). Until this lands, the workflow framework can't claim "clone is workflow-driven" — only "the most-common clone path is."

### 3.3 B08 / B09 / B10 — **all pending**
Recommendation: **B08 + B10 are the highest-leverage remaining work** per the diagnosis. B09 depends on both. Order:
1. B08 first (server-side packs + endpoint + client consumer).
2. B10 in parallel (migration command for old vaults — independent track).
3. B09 after B08 (per-mode clones consume the new pack flavours).

### 3.4 B14 (plugin system) and B15 (push/pull/fetch) — **late-sprint work**
Both depend on B13 (done) but should land after B08 stabilizes. Not blocked, just lower priority than the perf wins.

### 3.5 Top-level cruft — **product decisions needed**
Recommendation: short Architect+Designer review (~1h) to decide placement of `stash`, `remote`, `send`, `receive`, `publish`, `export`. Then a tiny brief to do the moves.

---

## 4. Brief updates needed

| Brief | Update |
|---|---|
| B06 | Add a "B06b" addendum noting `clone_read_only` and `clone_from_transfer` are NOT yet workflow-driven; commit to fold-in plan. |
| B08 | No update needed — the diagnosis doc reinforces it as the headline fix. |
| B09 | Update prerequisites — note that `clone_read_only` (the read-only-on-disk variant) is distinct from `clone-headless` and partly already shipped via Brief 05; clarify what remains. |
| B10 | **Strengthen** — the case-study diagnosis confirmed migration is the path to dedup for old vaults. Make explicit: the migration command's first real migration should re-encrypt tree objects with deterministic IVs (HMAC-derived). |
| B14 | Minor — note that several read-only namespaces (`history`, `inspect`, `file`, `check`) are now in dedicated `CLI__<Namespace>.py` files, ready to be plugin-ised. |
| B15 | Minor — note that `Vault__Sync__Pull` and `Vault__Sync__Push` already exist as separate sub-classes under `core/actions/`. |

---

## 5. New briefs to add

Six small briefs surfaced from this audit. Numbered B16–B21 (continuing the v0.12.x sequence):

| # | Brief | Owner | Effort | Priority |
|---|---|---|---|---|
| B16 | **Resolve Vault__Crypto → network dep** (Violation A from §2.1) | Architect + Dev | ~2h | Low — tracked as known violation |
| B17 | **Relocate `Vault__Transfer.py` to `core/actions/transfer/`** (Violation B) | Architect + Dev | ~½ day | Medium — eliminates 6 known-violation entries |
| B18 | **B06b — fold `clone_read_only` + `clone_from_transfer` into `Workflow__Clone`** | Dev | ~1 day | High — completes the workflow promise |
| B19 | **Fix `Safe_Str__Read_Key` type smell** (§2.4) | Dev | ~1h | Low |
| B20 | **B23 carry-forward — `Vault__Graph_Walk` + `batch_download` extraction** | Dev | ~1.5 days | Medium — sets up B08 cleanly |
| B21 | **Top-level CLI cruft cleanup** (`stash`, `remote`, `send`, `receive`, `publish`, `export`) | Architect + Dev | ~½ day | Low — needs design decision first |

**Plus the recommended next-mover:**

| | | |
|---|---|---|
| B22 (NEW) | **Workflow exception-typing fix** (§2.2 concern 2) — propagate typed exceptions instead of swallowing into RuntimeError | Dev | ~2h |

---

## 6. Recommended next moves

If the team has bandwidth for two parallel tracks:

**Track A — Performance (high leverage):**
1. **B08** (server clone packs) — primary fix per B07 diagnosis. Largest and most-impactful brief in the sprint.
2. **B09** (per-mode clones) — depends on B08.

**Track B — Correctness + cleanup (sequential, smaller):**
1. **B19** (Safe_Str__Read_Key) — 1h, quick win.
2. **B22** (workflow exception typing) — 2h.
3. **B18 (B06b)** (fold read-only + transfer clones into workflow) — completes B06.
4. **B20 (B23 carry-forward)** — Vault__Graph_Walk + batch_download dedup; sets up B08 cleanly.
5. **B17** (relocate Vault__Transfer) — eliminates 6 known violations.
6. **B10** (migration command) — runs anytime; high value for old vaults.
7. **B14** (plugin system) — late-sprint.
8. **B15** (push/pull/fetch generalize) — late-sprint.
9. **B16** (Vault__Crypto → network dep) — last; lowest priority.
10. **B21** (top-level cruft) — pending product decisions.

Track B can land while B08 is being designed.

---

## 7. Process observation

The two-session executor + reviewer model is producing high-quality work:
- 10 merges in ~2 days
- Each with a logged review entry
- Style violations consistently caught (multi-paragraph docstrings, module-level functions, bare instantiations, raw `Safe_Str` for ID fields)
- Production fixes applied during review (e.g., `_pull_stats_line` duplication caught in B13)

**The pattern works.** Recommend continuing it for B08+B10 (the biggest remaining briefs).

---

## 8. What this review does NOT do

- Re-run the full test suite for coverage (collected: 3,005 tests; layer test passes; not yet measured % coverage post-B13).
- Audit every step file (sampled `Step__Clone__Derive_Keys`, `Step__Clone__Walk_Trees`, `Workflow__Runner`).
- Audit per-sub-class moves (B13 produced 12+ moves; sampled `Vault__Sync__Clone`).
- Make any source changes.

A QA agent should run a fresh coverage measurement and confirm we're still at 98%+ post-restructure. If it dropped, that's a Phase-B-acceptance-style mini-gate worth running.
