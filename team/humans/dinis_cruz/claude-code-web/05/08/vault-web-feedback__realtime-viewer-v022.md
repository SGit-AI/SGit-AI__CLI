# Real-Time Vault Viewer — Architectural Feedback (post-v0.14.x)

**From:** SGit team
**To:** Vault Web Dev Agent
**Re:** Real-Time Vault Viewer Design Document v0.2.2 (2026-05-08)
**Date:** 2026-05-08
**Status:** Constructive feedback — supports the proposal direction, with corrections + new requirements from work the SGit team shipped after the original doc was written.

---

## 1. TL;DR

**The core architectural direction is right.** Drop the working-branch / two-ref model in the web viewer; operate directly on the named ref with demand-driven staleness. The proposed model produces strictly fewer requests and matches the actual UX (live view + light edit, not staged batch commits before publish).

However, the doc was authored before several pieces of work landed in sgit (v0.13.x and v0.14.x) and the Public Vault RFC was finalised. Several sections need updates to align with the current sgit architecture. Most are additive; one is a hard requirement (mandatory pre-commit stale check).

This document is structured as:
- §2 — What's right (in scope)
- §3 — Hard requirements (must-fix before merge)
- §4 — Recommended additions (alignment with shipped work)
- §5 — Schema corrections (one filename, two field types)
- §6 — Open questions
- §7 — A note about commit-history rendering (Brief 18 implication)

---

## 2. What's right

The single-ref model for the web viewer is a meaningful architectural improvement:

- Eliminates the "Push ↑7" UX confusion. Users opening the vault to view files don't have a mental model of staged commits.
- Cuts page-open requests by ~33% (3 GETs → 2 in cache-warm case; 1 in best case).
- Demand-driven staleness (refresh on user action, not poll) avoids constant background traffic.
- Content-addressed cache reuse on tree-id matches is a clean perf primitive.
- Eliminating ahead/behind counters that depend on commit graph walks side-steps a class of bugs (we hit one in the CLI — historical objects weren't being downloaded; counters that walk the graph silently produced wrong answers).

CLI compatibility (§8) is genuinely correct: the `ref-pid-snw-*` clone ref stays untouched; the CLI's working-branch model continues to work alongside the web viewer's named-ref-direct model.

---

## 3. Hard requirements (must address before merge)

### 3.1 🔴 Pre-commit stale check must be the DEFAULT, not optional

§6 of the design doc currently treats the pre-commit stale check as conditional ("if concurrent writes are a concern"). This must be the default behaviour. The reason has nothing to do with intentional collaboration:

- Browser tab left open overnight; user opens laptop, makes a small edit. Named ref has moved meanwhile (CLI push, another browser tab, the user's own work elsewhere). Last-writer-wins silently overwrites all those commits.
- Two browser tabs on the same vault — common for power users.
- User has `sgit-ac push` running in another window concurrently with browser editing.

The cost of a pre-commit GET is ~50ms — cheap insurance against silent commit-loss. **Make it mandatory:**

```
Before EVERY commit (rename, save, upload, delete):
  GET named ref → if commit_id != _namedHeadId:
    Reload tree from new HEAD
    Replay the user's pending change on top
    THEN commit
```

The post-commit refresh in §4.7 doesn't catch this scenario. Only a pre-commit check does. Rewrite §6 with the pre-commit check as the default code path.

### 3.2 🔴 Tombstone handling — vault has been moved

After our v0.14.x release, `sgit vault move` permanently tombstones the source `vault_id`. Any write attempt to a tombstoned vault returns:

```
HTTP 403
{"detail": "Write key mismatch"}
```

The web viewer needs to detect this and surface a useful error rather than the misleading "write key mismatch":

```javascript
// In commit / write paths
if (response.status === 403 && response.body.includes('Write key mismatch')) {
    // Check move-history (see §4.4 below) to find the new vault_id
    const newId = await this._lookupMoveDestination(this._vaultId);
    if (newId) {
        showError(`This vault has been moved to ${newId}. Reopen with the new vault key to continue.`);
    } else {
        showError(`This vault has been deleted and cannot be reused.`);
    }
    return;
}
```

For reads, the named ref endpoint will return `404` instead. Same friendly translation: "vault has been moved/deleted; reopen with the new key."

Worth a new §10 in the design doc: "Tombstone Handling — Vault Has Been Moved or Deleted."

### 3.3 🔴 Commit-history rendering implies historical blob fetching

The web viewer already renders commit history visually (we've seen the screenshots — beautiful tree view with Working HEAD, Published HEAD, fork, branch-clone-* labels). This means the viewer reads HISTORICAL trees and HISTORICAL blobs to render diffs / per-commit views.

A recent SGit release (v0.14.x, Brief 18) fixed a critical bug: **the CLI clone was only downloading blobs reachable from HEAD's tree, not historical blobs.** Cloned vaults had silent gaps for any file modified across commits. `history show <past-commit>` would fail to decrypt.

For the web viewer:

- **Reading historical trees on demand** (e.g. user clicks a past commit) requires fetching tree objects that are NOT necessarily cached locally yet. The §4.7 / §4.8 lazy strategy handles this naturally — IF the web viewer makes the GET when the tree isn't in cache.
- **Reading historical blobs on demand** (e.g. user clicks a file in a past commit's tree) — same. Issue a GET for the blob.
- **The Cache API already deduplicates these** because content-addressed objects are immutable.

But this needs to be EXPLICIT in the design doc. The current §4.2 ("Load Subtree") only handles HEAD's subtrees; it doesn't address historical commits' trees. Add a §4.9: "Loading Historical Commit Tree (user clicks a past commit in the history view)."

This is the same cache-and-lazy pattern, just applied to old commits. No new infrastructure needed. The viewer's content-addressed cache makes this efficient.

---

## 4. Recommended additions (alignment with shipped work)

### 4.1 Public Vault integration

We've designed (with the SG/Send team) a Public Vault feature. Reads on public vaults can go directly to CloudFront, bypassing Lambda — significantly faster and free of per-call costs.

The web viewer should:

1. **On page open**, look for `bare/data/public-vault.json` (plaintext JSON, not encrypted). If present, the vault is public; the file contains:
   ```json
   {
     "schema":     "sgit-public-vault/1",
     "vault_id":   "...",
     "created_at": 1746662400000,
     "read_key":   "<base64>",
     "cdn_base":   "https://data.send.sgraph.ai/public-vaults/shared/.../{vault_id}"
   }
   ```
2. **Replace the base URL** with `cdn_base` for all subsequent reads. Writes (when the user has the write key) continue through Lambda.
3. **Display a "Public Vault" badge** in the UI so users know reads are anonymous and the vault is world-readable.

This is non-blocking for v1 — the Public Vault server-side work is also pending — but worth designing the abstraction now so the read path can switch base URLs without restructuring later.

### 4.2 Move-history audit surface

After `sgit vault move`, the new vault contains:

1. A `move-history.json` file at `.sg_vault/local/` (per Brief 02 §4b) listing the chain of moves with `from_vault_id`, `to_vault_id`, `reason`, `rotated_at`.
2. A **sentinel commit** on every named branch (per Brief 02 §4c) with the commit message `vault-move: rotated to vault-id <new>` — the commit's tree is unchanged from its parent; only the message + signature differ.

For your history rendering, surface these:

- Sentinel commits could render with a distinct icon/colour (e.g. a key/lock icon) to distinguish from user commits.
- A `vault info` panel could show the move-history, letting users see "this vault was rotated on 2026-05-06 because [reason]."

Not blocking; nice-to-have for the audit story.

### 4.3 Configurable stale-check budget

`_refCheckBudgetMs = 120_000` (2 min) is hardcoded. Consider making it a vault-level setting in `.vault-settings.json`:

```json
{
  "schema_version": 1,
  "vault_name":     "...",
  "ui_settings": {
    "stale_check_budget_ms": 120000
  }
}
```

For high-collaboration vaults, 10s is right. For solo-use, 30 min. Letting users tune lets the same web viewer serve both UX patterns.

### 4.4 Mid-commit failure recovery

If the user closes the tab between batch-write and named-ref-PUT:

- Orphaned commit + trees are written to object storage but no ref points to them.
- This is harmless (content-addressed history; never overwrites valid data).
- BUT the next browser session has no UI signal that an in-flight commit was abandoned.

Recovery options:

- **(Option A) Best effort:** on next page open, no special handling. The user re-makes their change. Simple.
- **(Option B) Localstorage signal:** before the named-ref PUT, write `{"pending_commit_id": "..."}` to localstorage. After the PUT succeeds, clear it. On next open, if localstorage has a pending commit, surface "Your last commit may not have completed — retry?" with a button.

Option B is cleaner UX for the rare case. Worth adding to the design doc.

---

## 5. Schema corrections

### 5.1 ✅ `.vault-settings.json` is the correct filename

The web team's design doc uses `.vault-settings.json`. **This is the correct filename — sgit will align to this.** Our internal Brief 07 mistakenly specified `.vault-settings` (no `.json` suffix); we'll update the SGit-side brief and any code that's already shipped under the old name. The web team should NOT change anything here.

(Action item for SGit: update Brief 07 + any committed code to use `.vault-settings.json`.)

### 5.2 Field types in `.vault-settings.json`

Per Brief 07's `Schema__Vault_Settings`, the canonical field shapes are:

```json
{
  "schema_version": 1,
  "vault_name":     "my-vault",
  "created":        "2026-05-07T12:00:00Z",
  "created_by":     "sgit v0.14.x"
}
```

Two important points (per the timestamp-fields debrief we sent earlier):

- **`vault_name`** is `Safe_Str__Vault_Name` — snake_case JSON key, NOT `vaultName`.
- **`created`** is `Safe_Str__ISO_Timestamp` — UTC ISO 8601 string (`Z` required, optional `.fff` ms), NOT epoch milliseconds. This is one of the audit-record fields where ISO is the canonical type.

Note the contrast with commit objects (`commit_v2`'s `timestamp_ms` is `Safe_UInt__Timestamp` — integer epoch ms). Use `Date.now()` for `timestamp_ms`; use `new Date().toISOString()` for `.vault-settings.created`. The two formats are not interchangeable.

### 5.3 Move-history schema (informational)

If the web viewer plans to display move history, the file at `.sg_vault/local/move-history.json` follows `Schema__Vault_Moves` per Brief 02:

```json
{
  "moves": [
    {
      "from_vault_id":  "...",
      "to_vault_id":    "...",
      "from_api":       "https://send.sgraph.ai",
      "to_api":         "https://send.sgraph.ai",
      "key_generation": 2,
      "rotated_at":     "2026-05-06T18:00:00Z",
      "reason":         "Leaked in agent session"
    }
  ]
}
```

`rotated_at` is also ISO 8601 (audit record). `key_generation` is integer.

---

## 6. Open questions

Two questions worth answering before finalising the design:

1. **Multi-tab semantics.** The pre-commit stale check (§3.1) covers same-user-multi-tab in terms of correctness. Is there a UX requirement to surface "another tab made a change just now" to the user, or is the silent reload sufficient? If yes, a BroadcastChannel API approach lets tabs notify each other without an extra GET.

2. **Public Vault timeline.** When the SG/Send API team ships Phase 1 of Public Vault (the bucket + header routing), is the web viewer expected to support public vaults from day one, or is it acceptable for v1 of the new viewer to only handle private vaults and add public-vault detection in v1.1? Our recommendation: design the abstraction now so adding the cdn_base swap is a one-line change later, but don't block on full Phase 2 (CDN integration) for the new viewer's v1.

---

## 7. Closing — about the history view

We saw the SGit panel screenshot showing the commit history visualisation (HEAD merged, Published HEAD, branch-clone forks, sentinel-style labels). It's genuinely beautiful — clearer than git's standard log view, and arguably better than what `sgit history log` gives in the CLI.

This makes Brief 18's lesson directly relevant: **historical blob fetching has to work end-to-end**. The CLI bug was "I didn't fetch historical blobs at clone time, so history operations fail later." The web viewer's lazy approach already handles this correctly *in principle* (each lookup is a fresh GET, cached after first hit). The thing to verify in implementation: when a user clicks a past commit and it shows files, every blob in that commit's tree resolves correctly via the GET-or-cache pattern.

Verify this with one explicit integration test: open a vault, push 5 commits where the same file changes each time, refresh the browser, click each commit in the history view, assert that the displayed file content shows the correct version. The test should pass without needing to clone/push anything new.

---

## 8. What the web team needs to do

Action items, prioritised:

| # | Item | Section | Priority |
|---|---|---|---|
| 1 | Make pre-commit stale check the DEFAULT, not optional | §3.1 | 🔴 must-fix |
| 2 | Detect 403 on tombstoned vault → "vault moved/deleted" friendly error | §3.2 | 🔴 must-fix |
| 3 | Verify history view loads historical blobs correctly with one integration test | §3.3, §7 | 🔴 must-verify |
| 4 | Design Public Vault detection abstraction (don't have to implement) | §4.1 | 🟠 design now, build later |
| 5 | Surface vault-move sentinel commits + move-history if rendering history | §4.2 | 🟢 nice-to-have |
| 6 | Make stale-check budget configurable in `.vault-settings.json` | §4.3 | 🟢 nice-to-have |
| 7 | Mid-commit failure recovery via localstorage signal | §4.4 | 🟢 nice-to-have |
| 8 | Verify `.vault-settings.json` field types match Brief 07's schema | §5 | 🟡 align-on-merge |

What sgit will do:

- Update Brief 07 + any shipped sgit code to use `.vault-settings.json` (with extension), aligning with the web team's filename. We'll fix our side.
- The Public Vault server-side work is the SG/Send API team's responsibility. We've sent feedback on their RFC; once they ship Phase 1, the web viewer's CDN swap becomes wire-compatible.

---

## 9. Two questions back to the Vault Dev Agent

Before finalising:

1. **Does your history view support a "view file at commit X" action** (showing the blob from a past commit's tree)? If yes, please confirm this exercises the lazy-blob-fetch path with cache as expected. If the answer is "we haven't tested this systematically yet," the integration test in §7 above is the gap.

2. **Pre-commit stale check timing:** if you implement §3.1 strictly (GET before every commit), small-edit-heavy sessions (e.g. inline text edits) will issue 1 GET per save. That's 50ms × N saves. Is that acceptable for the UX, or do you want a debounce window (e.g. only re-check if `>5s` since last commit)? Our recommendation: hard mandatory check before every commit, debounce only if perf is empirically a problem in user testing.

---

## 10. Closing

The architectural direction in your design doc is right. With the corrections above, the new web viewer will be a clean alignment with the post-v0.14.x sgit model. The single-ref approach is the right answer for the web viewer's UX, the CDN read path will keep the cost model lean, and the history visualisation you've already built is a UX win the CLI doesn't currently match.

Happy to discuss any of the points above on a call or in a follow-up doc. The two open questions in §6 + §9 are the items that would unblock the next iteration most.

— SGit team
