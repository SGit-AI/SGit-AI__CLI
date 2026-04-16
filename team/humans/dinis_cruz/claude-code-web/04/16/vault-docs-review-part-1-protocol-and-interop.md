# Review of Vault Technical Docs — Part 1: Protocol & Interoperability Issues

**Date:** 16 April 2026
**Author:** Claude Code (SGit-AI__CLI session)
**Source docs reviewed:** `SGraph-AI__Tools/team/humans/dinis_cruz/briefs/04/15/from-team__vault/`
**Reviewed by:** SGit/CLI team (knows the Python implementation in detail)
**Part:** 1 of 2 — [Part 2: Implementation Gaps & Operational Notes]

---

## Overview

All 10 briefing documents (vault-index, protocol parts 1–5, dynamic-access parts 1–3, and the
handoff brief) were read and cross-checked against the Python CLI implementation in
`sgit_ai/sync/Vault__Sync.py`. The documents are accurate and well-written. The issues below
are real gaps in the protocol or interoperability risks — not documentation errors.

This part covers the four findings with the highest potential impact.

---

## Finding 1 — CRITICAL: `push()` Has No Compare-and-Swap (CAS)

### What the docs say

Protocol Part 5 §1 documents `push()` as:

```javascript
await this._refManager.writeRef(this._refFileId, this._headCommitId)
this._namedHeadId = this._headCommitId
```

A single unconditional PUT to the named ref. No check of the server's current state.

Protocol Part 5 §5 explicitly acknowledges the risk in Scenario B:

> "push() overwrites Z2 with Y2 ← SILENT DATA LOSS (current behaviour)"

### What the Python CLI does differently

`Vault__Sync.push()` uses a `write-if-match` header (CAS):

```
PUT /api/vault/write/{vaultId}/bare/refs/{refFileId}
Headers:
  x-sgraph-vault-write-key: {write_key}
  If-Match: {current_commit_id}   ← server rejects if ref has changed
```

The server returns `412 Precondition Failed` if the ref has moved since the client last read it.
The client then knows to fetch the new state and retry or surface a conflict to the user.

### The gap

| Implementation | Push behaviour |
|---|---|
| Python CLI (`sgit push`) | CAS — server rejects stale pushes |
| Web UI (`SGVault.push()`) | Unconditional PUT — silent overwrite |

Two web UI sessions working simultaneously on the same vault can silently destroy each other's
commits. The commit objects remain on the server (they're immutable blobs), but the named ref
pointer is lost. A user with the old commit ID can still recover — but without an explicit
rollback mechanism, data is effectively lost from the vault's visible history.

### When this matters

- Any vault accessed by two people simultaneously in separate browser tabs/windows
- Any integration that uses the web UI vault for shared document storage
- Vaults used in presentation mode while another user edits

### Recommended fix

The web UI `writeRef()` should include the current known commit ID as a conditional header:

```javascript
async writeRef(refFileId, commitId, expectedCurrentId = null) {
    const headers = { 'x-sgraph-vault-write-key': this._writeKey }
    if (expectedCurrentId) headers['If-Match'] = expectedCurrentId

    await this._sgSend.vaultWrite(
        this._vaultId, `bare/refs/${refFileId}`, headers, encrypted
    )
}

// In push():
await this._refManager.writeRef(
    this._refFileId, this._headCommitId,
    this._namedHeadId   // expect the server still has this
)
```

On `412 Precondition Failed`: surface an error to the user ("Someone else pushed while you were
working — pull first") rather than silently overwriting.

---

## Finding 2 — HIGH: Shared Clone Ref Across All Web UI Sessions

### What the docs say

Protocol Part 1 §2a documents `cloneRefFileId` derivation:

```javascript
HMAC(domain="sg-vault-v1:file-id:branch-ref:{vault_id}:web-ui")[:12 hex]
    → "ref-pid-snw-{hex12}"   (clone branch ref file ID)
```

The domain string `"web-ui"` is a fixed constant. Every web UI session for the same vault derives
the **same** `cloneRefFileId`.

### The problem

The clone ref (`ref-pid-snw-*`) tracks the local working state — which commit the current session
is at. It advances on every `commit()`.

If two browser tabs are open for the same vault:

```
Tab A: commit() → PUT clone ref → commit_C1
Tab B: commit() → PUT clone ref → commit_C2   ← silently overwrites Tab A's clone ref
Tab A: getAheadCount() → walks from C2, not C1 → wrong count
Tab A: push() → pushes C2, not C1 → Tab A's work is lost from named branch
```

The clone ref is a single-writer ref (`snw` = single-writer) but is being used as if it is
session-specific. With a fixed domain, it is effectively a shared resource with no access
control.

### Scope

- Any user who opens the same vault in two tabs simultaneously
- Any automated process that opens a vault alongside a human session

### What does not break

- The named ref (`ref-pid-muw-*`) is unaffected — it only moves on explicit `push()`
- File blobs and tree objects are immutable and unaffected
- A single-tab workflow (the common case) has no issue

### Recommended fix

The clone ref domain should include a session-unique component:

```javascript
const sessionId = crypto.randomUUID()   // generated once per SGVault instance
HMAC(domain=`sg-vault-v1:file-id:branch-ref:${vault_id}:${sessionId}`)
    → unique ref-pid-snw-* per session
```

Trade-off: session-specific clone refs are never cleaned up (no GC currently). With enough
sessions, the server accumulates orphan `ref-pid-snw-*` files. The current fixed domain avoids
this by design. The GC story needs to be resolved before changing the domain.

---

## Finding 3 — MEDIUM: Branch Index Path Mismatch (`bare/idx/` vs `bare/indexes/`)

### What the docs say

Protocol Part 1 §3 documents the branch index ID:

```
idx-pid-muw-{hmac[:12]}   stored at   bare/idx/{id}
```

Protocol Part 2 §1 Step 1 reads from:

```
GET /api/vault/read/{vaultId}/bare/idx/{branchIndexFileId}
```

### What the Python CLI does

In `Vault__Sync.py`, the branch index is written to `bare/indexes/{id}`, not `bare/idx/{id}`.
These are different server paths. The server stores them in different locations.

### The impact

| Feature | Impact |
|---|---|
| Single-branch vault (no branch index) | No impact — both clients 404 and fall back to the HMAC-derived `refFileId` |
| Multi-branch vault (branches created by `sgit`) | Web UI cannot see the branch index → always uses the default named ref → cannot switch branches |
| Web UI branch index written (if ever) | CLI cannot read it — `bare/idx/` vs `bare/indexes/` |

The 404 fallback saves single-branch vaults. But any vault that relies on the branch index for
multi-branch navigation is broken between implementations.

### The naming scheme docs are inconsistent

Protocol Part 1 §3 table shows `idx-pid-muw-*` stored at `bare/idx/{id}`. This is the web UI
path. The CLI uses `bare/indexes/{id}`. Neither document is wrong on its own — they describe
their own implementation — but together they reveal the interoperability gap.

### Recommended fix

Pick one canonical path and implement it in both. `bare/idx/` is shorter and consistent with the
`ref`, `data` segments already in use. The CLI should migrate from `bare/indexes/` to `bare/idx/`.

Migration: existing vaults with a `bare/indexes/` file need a one-time copy, or the CLI should
check both paths during the transition period.

---

## Finding 4 — LOW: `getAheadCount()` / `getBehindCount()` Walk First-Parent Only

### What the docs say

Protocol Part 5 §3 and §4 (and Part 2 §4 and §5) both show:

```javascript
cursor = commit.parents && commit.parents[0] ? commit.parents[0] : null
```

Only `parents[0]` is followed. Merge commits have two parents. The second parent line is never
walked.

### When this matters

If a merge commit (`"Merge current into local"`) ends up in the named branch history — which
happened routinely before the fast-forward fix — and a client does `getBehindCount()` starting
from a point *before* the merge, the walk along `parents[0]` may fail to reach the client's
known `_namedHeadId`. The loop runs to the 100-cap and returns 100 instead of the real count.

The **fast-forward fix** to `pull()` (implemented in `Vault__Sync.py` on this branch) eliminates
the main source of merge commits in the named branch. For vaults whose named branch history was
contaminated before the fix, the commit graph already has merge commits in it. Those vaults will
see incorrect ahead/behind counts until the contaminated history is rewritten or the named ref is
manually advanced past the merge.

### Correctness for the future

With fast-forward pull in place, the named branch should only ever receive merge commits when two
sessions genuinely diverged. In that case, `parents[0]` is the "theirs" side and `parents[1]` is
the "ours" side. Walking only `parents[0]` is a deliberate design choice (first-parent history),
not a bug — it gives a cleaner linear view. This is the same as `git log --first-parent`.

The only residual risk: if Finding 1 (no CAS on push) allows a session to overwrite the named
ref with a commit that has a different first-parent chain, `getBehindCount()` can return up to
100 even when the actual divergence is small.

### Recommendation

No immediate code change needed. Document that ahead/behind counts are first-parent only (as git
does) and add a note to the `getBehindCount()` docstring. Track separately as a future
improvement: walk both parent lines for a full divergence count.

---

## Summary Table

| # | Severity | Finding | Data loss? | Breaks existing vaults? |
|---|---|---|---|---|
| 1 | CRITICAL | Web UI `push()` unconditional PUT — no CAS | Yes, in concurrent push scenario | No, but ongoing risk |
| 2 | HIGH | Shared clone ref (`web-ui` fixed domain) | Clone ref confused; named branch safe | No |
| 3 | MEDIUM | `bare/idx/` vs `bare/indexes/` path mismatch | No | Multi-branch only |
| 4 | LOW | `parents[0]`-only walk in ahead/behind count | No | Pre-fix contaminated vaults |

---

*Part 2 covers VFS bridge asset loading gaps, settings blob orphan accumulation, and the
complete CLI dynamic-access spec review.*
