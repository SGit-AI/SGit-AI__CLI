# v0.13.x Mid-Sprint Review (Opus pass after Merges 1–4)

**Date:** 2026-05-05
**Reviewer:** Villager orchestrator (Opus deep audit)
**Scope:** All commits since v0.13.0 baseline (`88c627e`) through `1193638`. Reviewed against the v0.13.x brief-pack.

---

## Headline

| Metric | v0.13.0 baseline | After Merges 1–4 | Direction |
|---|---:|---:|---|
| Tests collected | 3,068 | **3,124** unit + **128** qa | Net +184 over baseline (+6%) |
| Suite warm time | ~70s parallel | (qa tier unchanged ≤ 80s gate) | Faster default loop |
| Briefs landed | 0 / 8 | **B01 ✅ B02 ✅ B03 ✅** + qa-tier split + step-coverage tests | 3 of 8 carry-forward briefs done |
| KNOWN_VIOLATIONS | 7 | 10 | Up by 3 (3 new dev-plugin core/workflow imports — flagged below) |

**Overall: high-quality work.** All four B01 fixes verified correct. Migration framework (B02) shipped with a meaningful first migration. Clone-readonly (B03) cleanly folded into the workflow framework. Reviewer caught two CLAUDE.md violation batches and fixed them. Test discipline strong.

**Three concerns to address** (none blocking; one should be flagged to the executor for the next pass).

---

## Per-brief findings

### B01 — Bug fixes (Merge 2)

✅ **All four fixes verified correct:**

| Fix | Verification |
|---|---|
| **B19 — `Safe_Str__Read_Key`** | New file at `sgit_ai/safe_types/Safe_Str__Read_Key.py` (regex `^[0-9a-f]{64}$`, exact_length=True); `Schema__Clone__State.read_key_hex` and `Step__Clone__Derive_Keys` both updated to use it. ✓ |
| **B22 — Workflow__Runner exception preservation** | `raise type(_exc)(error_msg) from _exc` at line 126; falls back to `RuntimeError` only if `_exc is None`. ✓ |
| **B04-1 — Context detection wired** | `CLI__Main.run()` calls `_detect_context()` at line 594, dispatches friendly-error path before `args.func(args)`. `_INSIDE_ONLY` includes `migrate` (which is correct). ✓ |
| **B15-1 — `_p` keyword fix** | Both `Step__Pull__Fetch_Missing.py:31` and `Step__Fetch__Fetch_Missing.py:31` use `_p=` (not `on_progress=`). Functional test at `tests/unit/workflow/pull/test_Step__Pull__Fetch_Missing__Functional.py` (95 lines, 3 tests) actually invokes the step against a real fixture. ✓ |

**Minor concern (B22):** `raise type(_exc)(error_msg) from _exc` requires the original exception's constructor to accept a single string. Most stdlib + most typed exceptions do, but **custom typed exceptions with multi-arg constructors will fail re-raise.** Worth adding a fallback: if `type(_exc)(error_msg)` raises, drop to `raise RuntimeError(error_msg) from _exc`. Small follow-up, not urgent.

### B02 — Migration framework (Merge 3)

✅ **Framework + first real migration shipped, 13 tests passing.**

**What's good:**
- `sgit migrate plan/apply/status` CLI works.
- `Migration__Tree_IV_Determinism` does the right algorithm: collect → topo-sort trees → re-encrypt bottom-up → topo-sort commits → rewrite commits → update refs → delete old trees.
- Idempotent for already-migrated trees (re-encrypting a deterministic tree produces the same ID; `tree_mapping` stays empty).
- Migration record persisted to `.sg_vault/local/migrations.json`.
- Tests exercise on-old-vault + on-new-vault + idempotency + dedup-improvement assertion.

**🟡 Three concerns to flag:**

1. **`try/except: pass` everywhere.** Five sites in `Migration__Tree_IV_Determinism.py` (lines 43, 127, 169, 244, 296) swallow exceptions silently. If a tree fails to decrypt (corruption), the migration silently skips it AND records "applied" successfully. **A legitimate vault corruption gets masked as a successful migration.** Should re-raise OR collect errors into the stats dict and surface them to the user.

2. **Topo-sort cycle fallback (lines 215–217 + 267–269)** appends any unsorted nodes at the end. Comment says "shouldn't happen in a valid vault" — but if it does, the migration silently reorders them arbitrarily. **A corrupted graph could produce subtly-wrong rewritten commits.** Should escalate (raise) instead.

3. **Branch index references not updated.** `_update_refs` only walks `ref_mgr.list_refs()` (the per-branch HEAD refs). The branch index file (`bare/indexes/<index-id>`) lists branches with embedded `head_ref_id` that points to ref files, NOT directly to commits — so this is probably fine for refs. But verify: are there any direct commit-id references inside `Schema__Branch_Index` that need updating? Quick check needed.

**🟡 One smell:**

4. **`is_applied` samples 5 trees** (line 35). For a vault with 1000 trees, 3 random-IV outliers, the sample could miss them. Returns True, migration is marked applied, but those 3 trees stay random-IV. **Mitigation:** the cost of "false-applied" is just suboptimal dedup, not corruption. Acceptable. But worth a comment in the code explaining the heuristic.

5. **Migration runner returns raw `dict`/`list[dict]`** (lines 47, 63, 73 of `Migration__Runner.py`). The brief specified `Schema__Migration_Record` and `Schema__Migrations_Applied`. The schemas exist (`sgit_ai/schemas/`) but the runner reads/writes JSON without using them. **Not enforced via Type_Safe round-trip.** Same pattern as v0.10.30's pre-schema state files. Worth addressing in a follow-up.

6. **`Migration__Registry` is hardcoded to one migration.** The brief expected auto-discovery (similar to the workflow registry from B05). For v1 with one migration this is fine; flag as future work when a second migration arrives.

### B03 — Clone-readonly into workflow (Merge 4)

✅ **Excellent work. The single largest gap from the Opus mid-sprint review (the parallel `clone_read_only` + `clone_from_transfer` paths) is closed.**

**What's good:**
- `Vault__Sync__Clone` shrunk by ~285 lines (from 446 → 262). All four clone variants now go through the workflow framework.
- `Workflow__Clone__ReadOnly` (9 steps) reuses 7 steps from the full workflow + 2 new read-only-specific steps (`Set_Keys`, `Setup_Config`).
- `Workflow__Clone__Transfer` (6 steps) cleanly handles the SG/Send token-based clone flow.
- `Transfer__Workspace` and `Schema__Transfer__State` properly typed.
- Both new workflows auto-register via `@register_workflow` decorator — ALSO solves Sonnet debrief §7.4 ("`sgit dev workflow list` should auto-discover").
- 45 new tests across both workflows.

**Reviewer fix 2 was substantial and good:** 5 monkeypatches + 6 `unittest.mock.patch.object` calls in `test_Vault__Sync__Clone__Coverage.py` were replaced with real fake-API subclasses inheriting `Vault__API`, plus a real local HTTP server for the large-blob path. **Zero mocks** in the final state. Strong review work.

**No concerns flagged. This is clean.**

---

## Cross-cutting findings

### KNOWN_VIOLATIONS went 7 → 10 (acceptable)

The three new entries are all `sgit_ai/plugins/dev/...` files importing `sgit_ai.workflow.*` and `sgit_ai.core.*`. **This is legitimate** — the dev plugin's job is to expose workflow internals for debugging/inspection, so importing from those layers is expected.

The test file's comment confirms they were added consciously:
```python
KNOWN_VIOLATIONS = {
    'sgit_ai/crypto/Vault__Crypto.py: imports sgit_ai.network.transfer.Simple_Token',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Object_Store',
    # ... 5 transfer entries ...
    f'{_DEV}/...: imports sgit_ai.workflow.X',
    f'{_DEV}/...: imports sgit_ai.core.X',
}
```

**Verdict: acceptable.** B06 will reduce the older 7 (Vault__Crypto + Vault__Transfer block). The 3 dev-plugin entries should stay.

### Test infrastructure work (Merge 1)

The qa-tier split (slow PBKDF2 / RSA tests moved to `tests/qa/`) is a clean win:
- Default loop runs 3,124 unit tests in ~70s.
- Slow tier has 128 tests run separately when needed.
- conftest shims at `tests/qa/{crypto,sync}/conftest.py` re-export the unit-tier fixtures so qa tests get the same fixture surface.

The `Workflow__Runner` JSON-emission bug fix (`record.json() + '\n'` → `json.dumps(record.json()) + '\n'`) is correct — `record.json()` returns a dict, not a string, so the previous code would have thrown TypeError on first transaction-log write attempt. **Good catch.**

### CLAUDE.md violations caught + fixed by reviewer (Merges 1, 2, 4)

- Module-level `_base_state()` functions in 3 workflow coverage test files → refactored to `class _S` instance methods.
- Multi-paragraph docstrings (1 step file, 1 schema file) → trimmed to single line.
- 5 monkeypatches + 6 mocks in `test_Vault__Sync__Clone__Coverage.py` → replaced with real Vault__API subclasses + local HTTP server.

**Reviewer is doing exactly the job this pattern needs.** Style violations are caught reliably; mock violations are caught and properly remediated (not just removed).

---

## Open items still pending

### From Sonnet debrief / Opus mid-sprint review

- ✅ **B19 (Safe_Str__Read_Key)** — done (Merge 2)
- ✅ **B22 (Workflow__Runner typed exceptions)** — done (Merge 2)
- ✅ **B04-1 (context detection wiring)** — done (Merge 2)
- ✅ **B15-1 (Fetch_Missing keyword arg)** — done (Merge 2) + functional test
- ⏳ **B15 signing key gap** — `Step__Pull__Merge` doesn't load signing key. Carried into B04 (push/pull/fetch wiring).
- ✅ **B15 workflow CLI registration** — `@register_workflow` decorator added in B03; auto-discovery now in place. Verify push/pull/fetch workflows also use this decorator when B04 lands.
- ⏳ **Upload_Objects DI gap** — 2 monkeypatched Vault__Batch tests removed (not refactored) in B01; deferred to B04.

### From this review (new findings)

- 🟡 **B22 fallback for non-standard exception constructors** — small follow-up; add `try / except TypeError → fall back to RuntimeError`.
- 🟡 **B02 silent error swallowing** — 5 `try/except: pass` sites in `Migration__Tree_IV_Determinism.py`. Should surface errors via stats dict or re-raise.
- 🟡 **B02 topo-sort cycle handling** — silent reorder on corrupt graph; should raise.
- 🟡 **B02 schemas not used by runner** — `Schema__Migration_Record` and `Schema__Migrations_Applied` exist but the runner uses raw dicts. Round-trip invariant not enforced.
- 🟡 **B02 branch index sanity check** — verify no commit-id refs inside `Schema__Branch_Index` need updating during tree-IV migration.

None block further work. Worth bundling into a small "B02 hardening" addendum if Dinis wants the migration polished before more vaults migrate.

### Still-pending v0.13.x briefs

- B04 push/pull/fetch wiring (depends on B01 ✅; ready to start)
- B05 per-mode clones (depends on B03 ✅; ready to start)
- B06 layer cleanup (independent)
- B07 CLI cruft (vault/share namespaces — independent)
- B08 workflow runtime polish (independent; auto-discovery already partly landed via @register_workflow in B03)
- v01–v07 visualisation track (independent)

---

## Recommendation

**Sprint is going well. Three suggested actions:**

1. **Flag the 5 B02 hardening items** to the executor as a small addendum brief (~½ day work). The migration command shouldn't go live to users with silent error swallowing.
2. **Continue current pace.** B04 / B05 / B06 / B07 / B08 are all unblocked. Visualisation v01 is unblocked. Reviewer pattern is proven.
3. **Consider running the v0.13.x suite end-to-end on the case-study vault** before more briefs land — confirm B01 fixes haven't broken anything operationally (not just at test level). Just a sanity check.

The dev team is doing high-quality work. The reviewer is catching what matters. The architecture is holding up. **No urgent escalations.** ⭐
