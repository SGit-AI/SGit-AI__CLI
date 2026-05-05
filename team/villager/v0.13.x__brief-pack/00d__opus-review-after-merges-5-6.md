# v0.13.x Mid-Sprint Review (Opus pass after Merges 5–6 — B04 + B05)

**Date:** 2026-05-05
**Reviewer:** Villager orchestrator (Opus deep audit)
**Scope:** Commits since `1193638` (last reviewed) through `2e78a0a`. Reviewed against the v0.13.x brief-pack briefs B04 and B05.

---

## Headline

| Metric | After Merges 1–4 | After Merges 5–6 | Direction |
|---|---:|---:|---|
| Tests collected | 3,124 unit + 128 qa | **3,174** unit (+ qa unchanged) | Net +50 |
| Briefs landed | 3 / 8 | **5 / 8** (B01/B02/B03/B04/B05) | Two more done |
| KNOWN_VIOLATIONS | 10 | 10 | Unchanged ✓ |
| New workflows registered | clone, clone-read-only, clone-transfer | + clone-branch, clone-headless, clone-range, pull, push, fetch | All 9 auto-discoverable |

**Overall: solid feature delivery, but one functional bug and one incomplete brief acceptance criterion.**

- B04 ships the pull/fetch workflow wiring with 20 functional tests.
- B05 ships clone-branch / clone-headless / clone-range with 28 functional tests.
- All 6 new workflows auto-register via `@register_workflow`.
- Reviewer Fix 3 caught docstring + `list[str]` typing issues (good).

**One P1 bug worth flagging to the executor before more pull traffic lands** (details in B04 section). One brief acceptance gap in B05 (lazy-fetch not wired to history commands) — should either land in a follow-up before users start using `clone-branch`, or be documented as a known limitation.

---

## Per-brief findings

### B04 — Push/pull/fetch wiring (Merge 5)

✅ **What's good:**

- `Vault__Sync__Pull.pull()` (`sgit_ai/core/actions/pull/Vault__Sync__Pull.py:69-98`) now delegates to `Workflow__Pull` cleanly. Old 200-line in-place implementation removed; preserves `_auto_gc_drain` + `_init_components` pre-check + legacy dict result shape.
- `Vault__Sync__Fetch` (`sgit_ai/core/actions/fetch/Vault__Sync__Fetch.py`) is a minimal 41-line facade — clean.
- All three workflows (`pull`, `push`, `fetch`) now `@register_workflow`-decorated; `sgit dev workflow list` will show them.
- `Schema__Pull__State` extended with `added_files` / `modified_files` / `deleted_files` / `conflict_paths` (typed `list[str]` after Reviewer Fix 3) so the merge step carries full diff information back through to the legacy dict adapter.
- `Step__Pull__Merge` now builds merge messages from real branch names (`f'Merge {named_branch_name} into {clone_branch_name}'`) — was previously hardcoded `'Merge remote changes'`.
- Functional tests are real — no mocks, real `Vault__Test_Env` snapshots.

🔴 **P1 bug — three fields populated then dropped before they reach the merge step:**

`Step__Pull__Load_Branch_Info` correctly populates three new fields needed by the merge step:
- `clone_public_key_id` — needed to load the signing key (B15 fix).
- `clone_branch_name`, `named_branch_name` — needed for the merge commit message.

But the next two steps construct fresh `Schema__Pull__State` instances and **do not copy these three fields through**:

| Step | File | Drops these 3 fields? |
|---|---|---|
| `Step__Pull__Fetch_Remote_Ref` | `sgit_ai/workflow/pull/Step__Pull__Fetch_Remote_Ref.py:39-52` | ✅ yes (constructs new state, no `clone_public_key_id` / `clone_branch_name` / `named_branch_name`) |
| `Step__Pull__Fetch_Missing` | `sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py:63-77` | ✅ yes (same omission) |
| `Step__Pull__Merge` | reads them — but always sees `None` | ⛔ |

**Consequences:**

1. **B15 signing-key fix is dead code.** `Step__Pull__Merge.py:110` reads `input.clone_public_key_id`; it's always `None` → `signing_key` stays `None` → merge commit is created **unsigned**. The fix Sonnet wrote (`Step__Pull__Merge.py:111-117`) never executes its happy path.
2. **Merge messages always use placeholder strings.** Lines 26–27 fall back to `'local'` / `'remote'`, so every three-way merge commit reads `'Merge remote into local'` instead of the real branch names. The improvement specified in the brief is silently neutralised.

No test caught this because:
- The pull functional tests assert `status` / `commit_id` / conflict counts but **don't inspect the merge commit's signature or message**.
- `grep signing_key` in `tests/unit/workflow/pull/` returns zero hits.

**Fix:** add `clone_public_key_id=input.clone_public_key_id`, `clone_branch_name=input.clone_branch_name`, `named_branch_name=input.named_branch_name` to the output schema construction in both `Step__Pull__Fetch_Remote_Ref.py:39-52` and `Step__Pull__Fetch_Missing.py:63-77`. Add a test that asserts the merge commit is signed and that the merge message contains the named branch name.

This is a one-line-per-step fix but is genuinely shipping unsigned merge commits today.

🟡 **Minor concerns:**

3. **`try / except: pass` on signing_key load** (`Step__Pull__Merge.py:113-117`). Once the field-dropping is fixed, a real `key_manager` exception (e.g. corrupted private key file) will be silently swallowed and the commit created unsigned. Should `workspace.progress('warn', ...)` at minimum so the user knows their merge wasn't signed.

4. **Six `try / except: pass` sites in `Vault__Sync__Pull._fetch_missing_objects`** (lines 156, 186, 237, 269, 291, 332). Same pattern flagged in the B02 review. API failures during BFS commit/tree walk are silently swallowed — `_find_missing_blobs` integrity check at the end of `Step__Pull__Fetch_Missing` (lines 49–59) catches the symptom (missing blobs) and surfaces a friendly error, which is a good safety net. But the underlying API error context is lost, so the user sees "object failed to download" without the actual reason.

5. **B22 follow-up still pending** — `raise type(_exc)(error_msg) from _exc` in `Workflow__Runner` will still break for typed exceptions with multi-arg constructors. Has not been touched in this round. Bundle into the cleanup pass at end of v0.13.x.

### B05 — Per-mode clones (Merge 6)

✅ **What's good:**

- Three workflows added with clear, minimal step compositions:
  - `Workflow__Clone__Branch` (10 steps): replaces `Walk_Trees` with `Walk_Trees__Head_Only`. ✓
  - `Workflow__Clone__Headless` (2 steps): just `Derive_Keys` + `Headless__Setup_Config`. Minimal, exactly as the brief specified. ✓
  - `Workflow__Clone__Range` (10 steps): swaps in `Walk_Commits__Range` with `range_from..range_to` exclusive-stop sentinel. ✓
- `Schema__Clone__State` extended with `bare`, `range_from`, `range_to`. Forwarded properly through `Step__Clone__Derive_Keys`.
- `Step__Clone__Extract_Working_Copy` honours `bare` flag (skip checkout). ✓
- `Vault__Sync__Base.fetch_tree_lazy(directory, tree_id)` implemented (`sgit_ai/core/Vault__Sync__Base.py:212-279`) with `.sg_vault/local/lazy-fetch.log` for observability.
- CLI parsers added for `clone-branch`, `clone-headless`, `clone-range` with `--bare` flag (rejected with clear error for headless).
- 28 new functional tests; range mode includes `with_explicit_range_to` test asserting commit ID match.
- All 6 clone workflows now in the registry: `clone`, `clone-read-only`, `clone-transfer`, `clone-branch`, `clone-headless`, `clone-range`.

🟠 **Brief acceptance gap — lazy-fetch infrastructure exists but is unwired:**

The B05 brief explicitly required (file: `team/villager/v0.13.x__brief-pack/brief__05__per-mode-clones-no-pack.md:39-43`):

> Plus a small lazy-fetch path:
> - `Vault__Sync.fetch_tree_lazy(tree_id)` — checks if the tree is in `bare/data/`; if not, downloads it via `api.batch_read([f'bare/data/{tree_id}'])`.
> - **Wire this lazy fetch into `Vault__Sync__Pull._fetch_missing_objects` and into the history-traversal commands** (`history log -p`, `history diff <past>`, etc.).

And acceptance criterion `:75`:
> `clone-branch` lazy-fetch tests: clone, then `history log -p`, assert lazy fetch was triggered.

**What landed:** `fetch_tree_lazy` method on `Vault__Sync__Base`, exposed via `Vault__Sync.fetch_tree_lazy`. Two tests that call it directly with a fake tree ID and assert it returns `False`.

**What's missing:** zero call sites in `sgit_ai/cli/`, `sgit_ai/plugins/`, or anywhere else (`grep -rn fetch_tree_lazy sgit_ai/cli sgit_ai/plugins` returns nothing). So today, after `sgit clone-branch`, running `sgit history log -p` on a past commit will silently fail to load older blobs (object not local) instead of triggering a lazy fetch.

**Impact:** clone-branch is functional only for HEAD reads. Any history-walking command on older commits will misbehave. The advertised "40-50× speedup" is real for the clone itself — but the user can't safely walk history afterwards.

**Recommendation:** before users start exercising `clone-branch` for real, either:
- (a) Wire `fetch_tree_lazy` into the file/history read paths (`Vault__Object_Store.load`-level fallback would catch most cases automatically), and add the brief's required `history log -p` test; OR
- (b) Document `clone-branch` as "HEAD-only — older history requires `sgit fetch` first" in the CLI help and acceptance.

(a) is the cleaner outcome and matches the brief's intent. Worth prioritising before B07/B08 land more changes.

🟡 **Minor concerns:**

6. **`Step__Clone__Walk_Trees__Head_Only` relies on BFS append order** (`sgit_ai/workflow/clone/Step__Clone__Walk_Trees__Head_Only.py:27`):

   ```python
   head_trees = root_tree_ids[:1] if root_tree_ids else []
   ```

   The accompanying comment correctly notes this works *only because* `Walk_Commits` BFS starts from `named_commit_id` and the very first append is HEAD's tree. If `Walk_Commits` ever changes to (say) iterate commits in timestamp order or do parallel fetches, this silently breaks — clone-branch would walk the wrong subtree, and tests would still pass because the shared fixtures have linear history. **Fix:** track HEAD's tree explicitly in `Schema__Clone__State.head_tree_id` (set in `Walk_Commits` from the first commit processed) and consume that in `Walk_Trees__Head_Only` instead of the `[0]` heuristic.

7. **`Step__Clone__Walk_Commits__Range` stop-sentinel is a single ID, not a set of ancestors.** `range_from` is excluded, but if you pass a commit that is *not* an ancestor of `range_to`, the BFS walks the entire history (no stop sentinel ever matches). Fine for the typical "head..tag" use case; could surprise a user who passes two unrelated commits. Worth a small comment in the step or a validation in the CLI handler that `range_from` is reachable from `range_to`.

8. **`fetch_tree_lazy` swallows API errors** (`sgit_ai/core/Vault__Sync__Base.py:245-246, 269-270`). If the API call fails partway through, returns `False` without surfacing why. Same try/except: pass pattern. At minimum, return a `Schema__Lazy_Fetch_Result(success: bool, error: str = '')` so callers can distinguish "all local" from "remote failed".

---

## Cross-cutting findings

### Mock discipline — still clean

`grep -rn 'monkeypatch\|Mock\|patch\.object' tests/unit/workflow/pull tests/unit/workflow/clone` on the new test files returns zero hits. Functional tests use `Vault__Test_Env` (real fixtures, real local server). Reviewer is enforcing this consistently.

### KNOWN_VIOLATIONS — unchanged at 10

No new layer violations introduced by B04 or B05. Both stayed within their proper layer boundaries (workflow → core → storage → crypto).

### Reviewer Fix 3 — caught what mattered

- 3 multi-paragraph docstrings trimmed (CLAUDE.md compliance).
- `Schema__Pull__State` `list` → `list[str]` (Type_Safe rule: typed collections, no raw `dict`/`list`).
- Review log updated with Merge 5 / Merge 6 / Reviewer Fix 3 entries.

The reviewer pattern is holding up. **Note:** the reviewer caught style violations but did NOT catch the field-dropping bug between Pull steps — because that's a semantic-level issue, not a style/violation issue. This kind of bug needs either an end-to-end test that asserts merge commits are signed, OR explicit "field forwarding" review of every step that reconstructs the schema. Worth adding to the reviewer's checklist.

### M6 mutation fix (commit `0cdef60`)

The `Fix stale M6 mutation + add detector test for read_key in clone_mode.json` commit added a detector for an attack on `clone_mode.json` (read-key tampering). Good defensive addition, no concerns.

---

## Open items still pending

### Still pending from previous Opus reviews

- ⏳ **B22 fallback for non-standard exception constructors** — flagged in 00c review, not yet addressed.
- ⏳ **B02 silent error swallowing** — 5 try/except: pass sites in `Migration__Tree_IV_Determinism.py`.
- ⏳ **B02 topo-sort cycle handling** — silent reorder on corrupt graph.
- ⏳ **B02 schemas not used by runner** — `Schema__Migration_Record` exists but `Migration__Runner` uses raw dicts.
- ⏳ **B02 sampling-only `is_applied`** — needs comment explaining heuristic.
- ⏳ **B02 branch index sanity check** — verify no commit-id refs need updating.
- ⏳ **Upload_Objects DI gap** — deferred to B04 by 00c review; no sign of it being addressed.

### New from this review

- 🔴 **B04 dropped fields in pull pipeline** — `clone_public_key_id` / `clone_branch_name` / `named_branch_name` lost between Step 2 and Step 5. Causes unsigned merge commits + placeholder merge messages. **Should fix before more pull traffic lands.**
- 🟠 **B05 lazy-fetch unwired** — `fetch_tree_lazy` exists but no call site. Brief acceptance criterion not met. Either wire it or document the limitation.
- 🟡 **B05 fragile `[:1]` HEAD tree heuristic** in `Walk_Trees__Head_Only`.
- 🟡 **B05 `Walk_Commits__Range` stop sentinel** — only safe when `range_from` is an ancestor of `range_to`.
- 🟡 **More try/except: pass sites** in pull/fetch pipelines (Vault__Sync__Pull, fetch_tree_lazy, signing_key load).

### Still-pending v0.13.x briefs

- B06 layer cleanup (independent; KNOWN_VIOLATIONS reduction).
- B07 CLI cruft (vault/share namespaces — independent).
- B08 workflow runtime polish (independent).
- v01–v07 visualisation track (independent).

---

## Recommendation

**Sprint pace is healthy, but two items need attention before more dependent work lands:**

1. **🔴 Fix B04 field-dropping bug** as a small follow-up commit (~15 min). Two-line change in `Step__Pull__Fetch_Remote_Ref` and `Step__Pull__Fetch_Missing`, plus a test asserting the merge commit is signed and the merge message names the branches. Without this, the entire B15-fix-via-B04 chain is dead code.

2. **🟠 Decide on B05 lazy-fetch wiring.** Either land the wiring as a small B05 addendum (1–2 hours: hook `fetch_tree_lazy` into `Vault__Object_Store.load` or the history command paths, plus the brief-required `history log -p` test) — OR document `clone-branch` as HEAD-only and explicitly defer the lazy-fetch wiring to a follow-up brief. Don't leave it ambiguous.

3. **Continue with B06/B07/B08/visualisation in parallel** once the above two are landed. The Reviewer pattern + functional-test discipline + workflow framework are all working well.

4. **Strongly suggest** adding a "field forwarding" check to the reviewer's brief-pack: every step that constructs a fresh `Schema__*__State` should explicitly forward (or recompute) every field its successors will need. This is the second time a step-pipeline correctness issue has surfaced (first was the parallel `clone_read_only` / `clone_from_transfer` paths in 00b); a checklist would catch them earlier.

The architecture is holding up. The two new findings here are localised, fixable, and don't change the overall trajectory. ⭐
