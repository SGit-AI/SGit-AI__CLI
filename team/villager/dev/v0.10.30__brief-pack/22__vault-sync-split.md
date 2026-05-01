# Brief 22 — `Vault__Sync.py` split (Phase 4 refactor)

**Owner role:** **Villager Architect** (design + boundaries) +
**Villager Dev** (mechanical extraction)
**Status:** **Last brief in the pack.** Multi-day. Do NOT start until
all of briefs 10–21 have landed and the test suite is at 89%+ coverage
with sub-80s parallel CI runtime.
**Prerequisites:** ALL prior briefs in the pack.
**Estimated effort:** **3–5 days**, not hours. This is the largest
brief.
**Touches:** `sgit_ai/sync/Vault__Sync.py` (the 2,986-LOC file) plus
new sibling modules under `sgit_ai/sync/` and possibly `sgit_ai/objects/`.

---

## Why this brief exists

Per Dinis decision 4: **Vault__Sync.py split is Villager-led, agreed
massively risky.** A single class hosting the entire sync surface (clone,
pull, push, fetch, write, probe, rekey, delete-on-remote, sparse,
diff, status) at 2,986 LOC is a foreseeable production accident.

Architect finding 04 documented:
- Two BFS implementations (clone vs pull) with diverging optimisations.
- Two near-identical 90-line `Vault__Sub_Tree.build*` methods (the
  HMAC-IV change had to be applied to both in lockstep).
- Three "encrypt-blob-or-reuse" sites.
- Eight candidate sub-classes.

Dev finding 06 reached the same conclusion from the code-quality angle
(8+ logical responsibilities, single-file file size).

The proposed extractions:
- `Vault__Graph_Walk` — unify the two BFS pipelines.
- `Vault__Object_Store` — encrypt-blob-or-reuse + blob bucketing.
- `Vault__Sub_Tree` consolidation — unify the two `build*` methods.
- Plus 5 more candidates from the findings.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/04__duplication-and-pipeline-shape.md`
   — the hit-list. Treat as authoritative for the proposed splits.
3. `team/villager/dev/v0.10.30/06__file-size-and-class-seams.md` — the
   eight + four candidate sub-classes.
4. `team/villager/architect/architect__ROLE.md` — Villager Architect
   reminder: "Architecture is frozen from Explorer." This split is
   ALLOWED because Dinis explicitly opted in (decision 4); it is a
   structural refactor that preserves behaviour, not a redesign.
5. The actual 2,986-LOC file. Read it fully (yes, fully). You cannot
   refactor what you haven't read.

---

## Scope

**In scope:**
- Architect produces a **detailed extraction plan** as a separate doc
  before any code moves. Plan includes:
  - For each proposed extraction: source line range, new module name,
    public-method-list, dependency graph.
  - Sequencing: which extraction first (suggest: `Vault__Graph_Walk`
    because it's the most duplication-heavy).
  - Test-coverage strategy: every extracted method must have at least
    its current coverage maintained; ideally direct unit tests added
    against the new public surface.
  - Roll-back strategy: each extraction is one commit, revertible
    independently.
- Dev executes the extraction plan one extraction at a time, with
  small commits.
- Verification after each extraction:
  - Full suite passes 2,105+ tests.
  - Coverage ≥ post-brief-18 number (should be ≥ 89%).
  - Phase B parallel CI shape still passes (≤ 80s combined).
  - No CLI command behaviour changed (check via integration tests).

**Out of scope:**
- Changing the sync protocol, vault format, CLI output, or any
  user-visible behaviour. **Behaviour preservation is non-negotiable.**
- Changing the API contract.
- Rewriting algorithms. This is structural extraction, not algorithmic.

**Hard rules:**
- One extraction per commit. The whole brief should produce 8–12
  commits, not one big commit.
- Each commit independently revertible.
- Suite green at every commit boundary.
- No source rename without a deprecation alias unless Dev confirms zero
  external callers (this is a CLI; "external callers" means scripts
  documented in `team/humans/dinis_cruz/`).

---

## Process

### Phase 1 — Architect plan (~1 day)

Architect writes:
`team/villager/architect/v0.10.30__vault-sync-split-plan.md`

Sections:
1. Inventory of 2,986 LOC by responsibility (line ranges per method
   group).
2. Proposed extractions (the 8+4 from the findings, prioritised).
3. For each extraction: name, target file, public surface, callers,
   dependency edges.
4. Sequencing: extraction #1 first (lowest-risk, highest-leverage).
5. Test-strategy per extraction.
6. Roll-back protocol.
7. Acceptance per extraction (suite green, coverage flat-or-up,
   parallel CI ≤ 80s).

Architect plan reviewed by Dinis before Dev starts mechanical work.

### Phase 2 — Dev mechanical extraction (~2–4 days)

For each extraction in sequence:
1. Create the new module file with the extracted symbols.
2. Replace the moved code in `Vault__Sync.py` with imports from the
   new module.
3. Run full suite + coverage + parallel CI.
4. If green, commit + push.
5. If not green, revert and escalate to Architect.

### Phase 3 — Final verification (~½ day)

- Full integration-test sweep (Python 3.12 venv).
- Coverage report on the new module set.
- LOC budget per file: target no file > 1,000 LOC after the split.
- Closeout report at `team/villager/architect/v0.10.30__vault-sync-split-final.md`.

---

## Acceptance criteria

- [ ] Architect plan written and Dinis-approved before Dev starts.
- [ ] Every extraction is its own commit.
- [ ] Suite green at every commit boundary.
- [ ] Coverage ≥ post-brief-18 baseline at every commit.
- [ ] Parallel CI ≤ 80s at every commit.
- [ ] No `sgit_ai/sync/Vault__Sync.py` file exceeds 1,000 LOC after the
      split (one file may stay larger if Architect documents why).
- [ ] No CLI command output / format / behaviour changed.
- [ ] Final closeout report committed.

---

## Deliverables

1. Architect plan doc.
2. New sibling module files under `sgit_ai/sync/` (and elsewhere as
   designed).
3. Refactored `Vault__Sync.py` (smaller).
4. Closeout report.

Commit message template (per extraction):
```
refactor(sync): extract Vault__Graph_Walk

Closes Architect finding 04 extraction #1. Unifies the two BFS
pipelines (clone vs pull) into a single Vault__Graph_Walk class.
~140 LOC removed from Vault__Sync.py; new module ~180 LOC.

Behaviour preservation: full suite passes 2,105 tests; coverage flat;
parallel CI under 80s.

Part of brief 22 Vault__Sync.py split.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 400-word summary:
1. Number of extractions completed.
2. Final per-file LOC table.
3. Coverage delta.
4. Parallel CI delta.
5. Any extraction that was deferred (and why).
6. Recommended next refactor candidates for v0.11.x (if any).
