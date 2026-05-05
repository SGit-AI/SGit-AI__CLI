# Brief B07 — Diagnose: Case-Study Vault

**Owner role:** **Villager Dev** + **Villager Architect** (interpret findings)
**Status:** BLOCKED until brief B01 lands.
**Prerequisites:** B01 (instrumentation tools) merged.
**Estimated effort:** ~3–4 hours
**Touches:** new diagnosis report doc only. No source changes.

---

## Why this brief exists

Strategy doc lists 5 hypotheses (H1–H5) for where the 184s of tree
walking goes. Brief B01 ships the tools to measure. This brief uses
them on the case-study vault and produces a numbers-grounded diagnosis
report that informs brief B08's pack design.

**Post-v0.12.0 note.** The 184s tree-walk metric was captured against
v0.11.x. v0.12.0 didn't change the clone path's algorithmic shape (the
`Vault__Sync` split was structural — `_clone_with_keys` is now in
`Vault__Sync__Clone.py` but does the same BFS). So the diagnosis target
is still valid. **Re-run the baseline first** to confirm the number
didn't move incidentally. If it did, update this brief and proceed.

---

## Required reading

1. This brief.
2. `team/villager/v0.11__clone-perf-strategy.md` §2 (the 5 hypotheses).
3. `team/villager/v0.12.x__perf-brief-pack/01__sprint-overview.md`.
4. The Phase-0 tools shipped by B01: `sgit dev profile clone`, `sgit dev tree-graph`, `sgit dev server-objects`, `sgit dev replay`.

---

## Scope

### Step 1 — Establish baseline

Clone the case-study vault using the new `sgit dev profile clone` tool
in a clean tmp dir. Capture full JSON trace.

```
sgit dev profile clone <vault-key> /tmp/case-study --json /tmp/clone-baseline.json
```

### Step 2 — Hypothesis verification per H1–H5

For each hypothesis, run the corresponding tool / analysis and record:

**H1 — Many small BFS waves**
- From the JSON trace: count Phase-4 waves, plot wave-size distribution.
- Compute: total HTTP calls, average wave size, max wave size, min wave size.
- If avg wave size < 50, H1 is significant.

**H2 — Per-tree decryption + JSON-parse overhead**
- From the JSON trace: per-tree decrypt + parse times for top-100 trees.
- Compute: median, p95, total decrypt+parse time, ratio to total tree-walking time.
- If decrypt+parse dominates HTTP wall-clock, H2 is significant.

**H3 — Pre-HMAC-IV trees fail to dedup**
- Use `sgit dev tree-graph` to count unique tree-ids vs total tree references across history.
- Compute the dedup ratio. If ratio is low (e.g., <30% dedup), H3 is significant.

**H4 — Server response composition is slow per batch**
- From the JSON trace: per-wave HTTP wall-clock minus client-side decrypt time.
- This is "server time + network latency". If server time dominates, H4 is significant.

**H5 — Walking historical trees is unnecessary**
- Use `sgit dev tree-graph` to count: trees needed for HEAD only vs trees walked across history.
- Compute the ratio. If <10% of walked trees are needed for HEAD, H5 is the dominant lever.

### Step 3 — Diagnosis report

Produce: `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` (≤ 250 lines).

Sections:
1. Vault profile (commits, trees, blobs, vault age, structure).
2. Per-hypothesis verification with numbers + verdict (significant / minor / not-applicable).
3. Time attribution: where does the 184s go? Per-component breakdown.
4. Recommended fix priority (ranked).
5. Pack design implications: what should be in `head` vs `full` packs for THIS vault?
6. Anything unexpected: flag for Architect.

### Step 4 — (Optional) before/after comparison fixture

Save the clone trace JSON as a permanent fixture for brief B11 / future
regression tracking. The same vault re-cloned after brief B08 lands
should show measurable improvement.

---

## Hard constraints

- **Read-only.** No source changes. Only the report doc.
- **No mocks** in any analysis (trivially: no code being added).
- Use only the tools shipped by B01.

---

## Acceptance criteria

- [ ] Diagnosis report exists at the proposed path.
- [ ] Each hypothesis H1–H5 has a numerical verdict.
- [ ] Recommended fix priority is grounded in the numbers.
- [ ] Pack-design implications are explicit (informs brief B08).
- [ ] Trace JSON saved as a fixture (`tests/fixtures/perf/case-study-clone-baseline.json` or similar).
- [ ] Closeout note added to `01__sprint-overview.md`.

---

## Out of scope

- Implementing any fix. This brief is diagnosis only.
- Running the same analysis on additional vaults (defer until packs land; then re-measure).
- Server-side measurement (would need backend access; flag if the diagnosis suggests it).

---

## Deliverables

1. Diagnosis report.
2. Saved trace JSON fixture.
3. Closeout note in sprint overview.

---

## When done

Return a ≤ 250-word summary:
1. Per-hypothesis verdict (significant / minor / not).
2. Time attribution (where does the 184s actually go?).
3. Recommended primary fix.
4. Pack-design recommendation for B08.
5. Anything unexpected that surfaced.
