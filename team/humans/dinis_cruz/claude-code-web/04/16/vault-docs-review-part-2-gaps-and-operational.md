# Review of Vault Technical Docs — Part 2: Implementation Gaps & Operational Notes

**Date:** 16 April 2026
**Author:** Claude Code (SGit-AI__CLI session)
**Source docs reviewed:** `SGraph-AI__Tools/team/humans/dinis_cruz/briefs/04/15/from-team__vault/`
**Reviewed by:** SGit/CLI team (knows the Python implementation in detail)
**Part:** 2 of 2 — [Part 1: Protocol & Interoperability Issues]

---

## Overview

This part covers findings that are not protocol-level risks but are important for teams building
on top of the vault: the VFS bridge's asset loading gaps, settings blob accumulation, a minor
documentation inconsistency, and a complete review of the CLI dynamic-access spec.

---

## Finding 5 — MEDIUM: VFS Bridge Does Not Intercept CSS Background Images

### What the docs say

Handoff Brief §3 documents the VFS bridge as handling:

| Asset type | Mechanism | Status |
|---|---|---|
| `fetch()` calls (JSON, CSS, JS, etc.) | `window.fetch` override | Working |
| `<img src="...">` assignments | `HTMLImageElement.prototype.src` setter | Working |
| `img.setAttribute('src', ...)` | MutationObserver | Working |
| CSS `background-image: url(...)` | Not intercepted | Not yet |
| `<script src="...">` | Not intercepted | Not yet |
| `<link rel="stylesheet" href="...">` | Not intercepted | Not yet |

The handoff brief acknowledges these gaps explicitly.

### Impact

Any HTML file in a vault that uses CSS `background-image: url(relative/path.png)` will fail to
render — the browser will attempt to load the image from the blob URL context, find no base URL,
and silently drop the image.

Similarly, `<script src="...">` and `<link rel="stylesheet" href="...">` loaded from relative
paths will not resolve. These are common patterns in slide presenter tools, HTML reports, and
documentation sites — exactly the use cases the vault viewer is targeting.

### The fix (as suggested in the handoff brief)

For CSS background images loaded dynamically (via `element.style.backgroundImage`), override the
CSS style setter — harder to intercept generically.

For `<link rel="stylesheet">` and `<script src="...">` in the HTML source, the correct approach
is to intercept them at parse time by transforming the HTML before creating the blob URL:

```javascript
// Before: <link rel="stylesheet" href="styles/main.css">
// After:  inline the CSS content as a <style> block

async function inlineAssets(htmlText, htmlDir, dataSource) {
    // Parse, find link/script tags with relative hrefs/srcs
    // Fetch each via dataSource.getFileBytes()
    // Replace with inline content
    return transformedHtml
}
```

This is more robust than runtime interception because it handles assets that the browser
processes before any JavaScript runs.

### Priority for Tools team

If the `sg-vault-browse` use cases include HTML pages with CSS stylesheets or background images,
this should be addressed before the VFS bridge is considered production-ready.

---

## Finding 6 — LOW: Settings Blob Re-encrypted on Every Commit

### What the docs say

Protocol Part 3 §2b documents `_commit()`:

> "Settings are always re-serialised and stored: `PUT .../bare/data/{settingsBlobId}`"
>
> "Settings are not stored as a special file type on the server. They live as a special
> `.vault-settings` entry in every root tree."

### The problem

Because `SGSendCrypto.encrypt()` uses a fresh 12-byte random IV per call, the same plaintext
settings JSON produces a different ciphertext every time. A different ciphertext means a
different `SHA-256(ciphertext)[:12]` → a different `obj-cas-imm-*` blob ID → a new blob stored
on the server.

Result: every commit writes a new settings blob, even if settings have not changed. On a vault
with 1000 commits, there are 1000 orphaned settings blobs on the server. They never get cleaned
up (no GC currently).

### Scale of the issue

```
Example: vault with 1 commit per day for 1 year
  → 365 settings blobs
  → typical settings blob: ~200 bytes (encrypted)
  → total orphan storage: ~73 KB

Example: active shared vault with 50 commits per day
  → 18,250 settings blobs per year
  → ~3.5 MB of orphan blobs per year
```

This is an efficiency concern, not a correctness issue. The correct settings are always in the
latest root tree. Old blobs are unreachable from any current commit chain.

### Recommended fix (low urgency)

Add a `content_hash` check before re-encrypting:

```javascript
const settingsJson = JSON.stringify(this._settings)
const settingsHash = await sha256hex(settingsJson)

if (settingsHash !== this._settingsHash) {
    // Settings actually changed — re-encrypt and store
    const newBlobId = await store(encrypt(settingsJson))
    this._settingsHash = settingsHash
    this._settingsBlobId = newBlobId
} else {
    // Settings unchanged — reuse existing blob ID
    // No new blob stored, no new PUT
}
```

This reduces settings blob writes to only when settings are actually modified (vault rename,
description change, etc.) — probably less than 1% of commits in practice.

---

## Finding 7 — INFO: Series Header Error in Protocol Part 1

### What the docs say

Protocol Part 1's header says:

```
Series: 1 of 3 — [Part 2: Read Protocol] [Part 3: Write Protocol]
```

But the actual series has 5 parts:
- Part 1: Crypto & Object Model
- Part 2: Read Protocol
- Part 3: init and commit
- Part 4: File and Folder Mutations
- Part 5: push and pull

The `1 of 3` and `[Part 3: Write Protocol]` references are from an earlier draft of the series
before it was expanded. Parts 2 through 5 all have correct `N of 5` headers.

### Impact

None — this is a copy-paste error in one header. All content is correct.

---

## Finding 8 — INFO: CLI Dynamic-Access Spec Review

### Background

Dynamic Access Part 3 §8 provides a complete specification for implementing `sgit cat`, `sgit
ls`, and `sgit warm` with on-demand access (no full clone needed). This is directly relevant to
the SGit/CLI team.

The spec is correct and matches the Python CLI's existing object model. Notes for the
implementation:

### `sgit cat` — 6 GETs regardless of vault size

The spec correctly counts 6 GETs for a 3-level-deep file:
```
1 ref GET + 1 commit GET + 3 tree GETs + 1 blob GET = 6 GETs
```

The Python CLI currently requires a full clone before `sgit cat` works. The spec describes
exactly how to bypass that. The `Vault__Sub_Tree.flatten()` code already walks the tree
recursively — the same logic can be applied to path-targeted walking for `sgit cat`.

### `sgit ls` — zero blob fetches

The spec correctly notes that `sgit ls` (directory listing) never needs to fetch file blobs.
Only tree objects are needed. This is much cheaper than `sgit clone`.

### Cache location spec

```
~/.sgit/cache/blocks/{vaultId}/{objectId}
```

This mirrors the browser Cache API key structure (`https://sgvault/{vaultId}/bare/data/{objectId}`)
with the hostname portion dropped. The content is identical: raw `[IV][ciphertext][tag]` bytes.

The `-imm-` guard translates directly:

```python
def is_cacheable(object_id: str) -> bool:
    return '-imm-' in object_id
```

This should live alongside the existing `Vault__Object_Store` or as a new
`Vault__Block_Cache` class.

### Interoperability note

Browser cache and CLI cache are separate (browser Cache API vs filesystem). A file fetched in
the browser is not in the CLI cache and vice versa. This is correct and expected. The caches
are format-compatible (same bytes) but have no sharing mechanism — they operate independently
on the same underlying server objects.

---

## What the Docs Get Exactly Right

These items were verified and are correct — worth noting because they are subtle:

1. **`_buildTreeEntries()` stub preservation** — Protocol Part 3 §2a correctly documents that
   unloaded folder stubs reuse their `_tree_id` unchanged during commit. This is the critical
   invariant that prevents data loss when committing while sub-folders are not loaded. The
   Python CLI has the same invariant and both implementations handle it correctly.

2. **Double-encrypted commit message** — Protocol Part 3 §2d notes that `message_enc` inside
   the commit JSON is encrypted separately, and the entire commit JSON is then encrypted again
   as the outer blob. This is belt-and-suspenders: even if the outer layer were broken, the
   message is still encrypted. Confirmed correct.

3. **`data.slice(0)` before cache put** — Dynamic Access Part 3 §4 explains why the ArrayBuffer
   is copied before being wrapped in a `Response` for the Cache API. Without the copy, a caller
   that transfers the buffer to a Web Worker would detach the original, and the cache would
   store an empty blob. The fix is correct and the explanation is accurate.

4. **`needsLoading()` edge case for new folders** — Dynamic Access Part 2 §7 correctly identifies
   that a freshly created folder (`createFolder()`) has `_loaded` undefined (not `false`) and no
   `_tree_id`. `needsLoading()` returns `false` for it correctly — it's an in-memory-only folder
   that needs no server fetch.

5. **`__sgVfs` flag lifecycle** — Handoff Brief §3 documents the critical detail that
   `__sgVfs = true` must be cleared after the async blob URL is applied. If left permanently
   true, the second `img.src` update on the same element falls through to the native setter
   and fails. The fix (set before request, clear in callback) is correct and critical for
   slide-navigation use cases.

6. **Expected 404s** — Handoff Brief §7 documents the two 404s that always appear on vault open
   (clone ref and branch index). These are correct behaviour, not errors. The explanations are
   accurate and match both the web UI and CLI implementations.

---

## Recommendations by Priority

| Priority | Finding | Owner | Effort |
|---|---|---|---|
| P0 | Finding 1: Add CAS to web UI `push()` | Web UI team | Low — one header |
| P1 | Finding 2: Session-unique clone ref domain | Web UI team | Low — one HMAC call |
| P1 | Finding 3: Align `bare/idx/` path in CLI | SGit/CLI team | Low — string change + migration |
| P2 | Finding 5: CSS background-image in VFS bridge | Tools team | Medium — HTML transform |
| P3 | Finding 6: Skip settings re-encrypt if unchanged | Web UI team | Low — hash check |
| P4 | Finding 4: Document first-parent walk as explicit choice | Web UI team | Trivial |
| P5 | Finding 7: Fix `1 of 3` header in Protocol Part 1 | Web UI team | Trivial |
| P5 | Finding 8: Implement `sgit cat`/`sgit ls`/`sgit warm` | SGit/CLI team | Medium |

P0 is the only item with active data loss risk in a live vault. P1 items are important for
correctness in multi-tab / multi-client scenarios. P2 blocks VFS bridge completeness for
real-world HTML content.

---

*This concludes the review of the 10 briefing documents from the SGraph-AI__Tools vault team.*
*All source documents are accurate descriptions of their respective implementations.*
*The issues above represent gaps between implementations or gaps relative to the intended use cases.*
