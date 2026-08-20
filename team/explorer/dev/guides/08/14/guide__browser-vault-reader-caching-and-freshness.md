# Guide — Reading a Live Vault From the Browser: Cache Tiers and the Freshness Window

**Date:** 2026-08-14 · **Audience:** anyone building a client-side vault reader (SG/Vault, an edge function, a static site), and the CLI team for §6
**Live example:** <https://sgit.ai/deploy/> — the deployment docs rendered there are **not part of that website**. They live in a vault maintained by the SG/Send team; the browser fetches ciphertext from `https://dev.send.sgraph.ai` over CORS and decrypts it in the tab.
**Claim under test:** a browser holding only `vault_id` + `read_key` can render a documentation site from a vault, and — with the right cache tiers — steady-state reading costs **zero network requests**, while a new commit still propagates within a bounded delay.

> In one sentence: object ids are SHA-256 of the **ciphertext**, so every object is immutable and cacheable forever by infrastructure that cannot read it; the ref is the only mutable thing, so it is the only thing that has to be refetched — and not on every page view.

This guide is the executable version of that claim. Each section says what to run and what observation would falsify it. Everything here is running in production on sgit.ai; the reader is `assets/vault-docs.js` in the [website repo](https://github.com/SGit-AI/SGit-AI__Website).

---

## 0. Prerequisites

Nothing but `curl` and a browser. The example vault is public **by construction**: its read key is published in `deploy/vault.json` on the site, because a read key is derived one way and cannot be inverted into write access.

```bash
export EP=https://dev.send.sgraph.ai
export VAULT=fyofmkvr
export READ_KEY=$(curl -s https://sgit.ai/deploy/vault.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["read_key"])')
```

> **Do not copy a read key into this repo.** Fetch it from the site at run time, as above. There is exactly one place it is published, and that is the point — see `docs/exposed-vault-key.html` on the site for what happens when a key ends up somewhere it was not meant to be.

**Note on auth:** this deployment serves `GET /api/vault/read/...` **without a token**. That is a server policy (reads default-allow), not a property of the format, and it is what makes a pure-browser reader possible with no secret beyond the read key. If a deployment flips reads to deny-by-default, a browser reader needs a token and the "publish a read key" pattern needs revisiting.

---

## 1. The read path, in four requests

Ids are computed locally; the server is never told what is being looked for.

```bash
# ref file id = 'ref-pid-muw-' + HMAC-SHA256(read_key, "sg-vault-v1:file-id:ref:<vault_id>")[:12]
REF=ref-pid-muw-$(printf 'sg-vault-v1:file-id:ref:%s' "$VAULT" \
  | openssl dgst -sha256 -mac HMAC -macopt hexkey:$READ_KEY -r | cut -c1-12)
echo "$REF"

curl -s -o /tmp/ref.bin -w 'ref: %{http_code} %{size_download}B\n' "$EP/api/vault/read/$VAULT/bare/refs/$REF"
```

Then, in order:

| # | Object | Path | What it gives you |
|---|---|---|---|
| 1 | ref | `bare/refs/ref-pid-muw-…` | `{"commit_id": "obj-cas-imm-…"}` — the only mutable object |
| 2 | commit | `bare/data/obj-cas-imm-…` | `commit_v1`: `tree_id`, `message_enc`, `parents`, `timestamp_ms` |
| 3 | tree(s) | `bare/data/obj-cas-imm-…` | `tree_v1`: entries with `blob_id`/`tree_id`, `name_enc`, `size_enc` |
| 4 | blob | `bare/data/obj-cas-imm-…` | the file |

Every payload is AES-256-GCM with the wire layout `IV(12) ‖ ciphertext ‖ tag(16)`, AAD none, key = the 32 raw bytes of the read key. The same bytes are the HMAC-SHA256 key for id derivation.

Decrypt in the browser with Web Crypto (this is the whole of it):

```js
const raw    = Uint8Array.from(readKeyHex.match(/../g).map(h => parseInt(h, 16)));
const aesKey = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt']);
const pt     = await crypto.subtle.decrypt(
  { name: 'AES-GCM', iv: bytes.slice(0, 12), tagLength: 128 }, aesKey, bytes.slice(12));
```

**Observe (falsifier #1 — derivation parity):** the id your browser computes must equal the one native CPython computes for the same vault. If they differ, the domain string or the truncation is wrong, and every request 404s with no other symptom. Verified for this vault: the browser and `sgit` agree on `ref-pid-muw-1493a12670c9`.

**Gotcha — secure context.** `crypto.subtle` is `undefined` outside a secure context. `https://` and `http://localhost` are fine; a fake `http://site/` origin in a test harness is not, and the failure looks like a bug in your code rather than a missing capability. Guard it and say so explicitly.

---

## 2. Why a first visit reads more than four objects

Filenames are encrypted **inside tree objects**, so building any kind of navigation means walking every directory. On this vault a cold load reads 18 objects (~14 KB) to render one page — 1 ref, 1 commit, 15 trees, 1 blob.

The path→blob index that walk produces is a **pure function of the commit id**. So it is memoised, keyed by commit:

```js
VaultReader.prototype.indexKey = function () {
  return 'sgit-vdocs-idx:' + this.vaultId + ':' + this.head;   // localStorage
};
```

Measured effect on sgit.ai: **18 rows → 4 rows** on a second visit to an unchanged commit — ref, commit, index (from memo), blob. Zero tree objects.

**Observe (falsifier #2):** the memo must be keyed by commit id, not by vault id. Keyed by vault, a new commit silently serves a stale index and pages resolve to blobs from the previous tree — a bug that looks like caching working perfectly right up until content changes.

---

## 3. The cache tiers

| Tier | Holds | Lifetime | Why it is safe |
|---|---|---|---|
| memory (`Map`) | decrypted objects | page session | avoids decrypting the same tree twice while navigating |
| Cache API | **ciphertext** of `obj-cas-imm-*` | until cleared | id is the hash of the ciphertext ⇒ can never be stale |
| localStorage | path→blob index | keyed by commit id | pure function of the commit |
| freshness window | the ref | `ref_ttl_s` (default 120 s) | the only mutable object; see §4 |

Note the second row stores **ciphertext**, not plaintext. The Cache API entry is as unreadable as the server's copy — which is what makes edge/proxy/CDN caching of private data coherent rather than reckless.

---

## 4. The freshness window on the ref

The ref must be refetched *sometimes* — that is how a new commit is noticed. It does not have to be refetched on **every page view**. So the last answer is kept for `ref_ttl_s` seconds:

```jsonc
// deploy/vault.json
{ "endpoint": "https://dev.send.sgraph.ai", "vault_id": "fyofmkvr",
  "read_key": "…", "ref_ttl_s": 120 }        // 0 = check on every page view
```

```js
VaultReader.prototype.refCached = function () {
  var rec = JSON.parse(localStorage.getItem(this.refKey()) || 'null');
  if (!rec || !rec.text || !rec.at) return null;
  if (Date.now() - rec.at >= this.refTtlMs) return null;      // window elapsed
  return rec;
};
```

Three consequences, and they are the whole trade:

1. **Steady-state reading costs nothing.** Everything else is content-addressed and cached; the one mutable object is inside its window.
2. **Server load stops scaling with page views.** It scales with *readers per window*: one 69-byte request per reader per two minutes, however much they read.
3. **Propagation is delayed, and bounded.** A new commit appears within the window at worst — and immediately on demand, because a forced check ignores the window entirely. That escape hatch is what makes the window safe to have; without it, "cached" and "wrong" become indistinguishable to the user.

Measured against a local mirror of the read API (browser, Chromium):

| Scenario | Vault requests |
|---|---|
| cold load, nothing cached | 18 (1 ref + 17 objects) |
| reload inside the window | **0** |
| five doc pages never opened before | 0 HEAD checks + 4 blobs (first read of each) |
| revisiting those same five pages | **0** |
| forced check ("check for new commit") | 1 (ref) — window ignored |
| reload after the window elapsed | 1 (ref) — refetched, as expected |

**Observe (falsifier #3):** a forced check must bypass the window *and* reset it, and clearing caches must drop the stored ref. If either leaks, a reader can be pinned to an old commit with no way out, which is strictly worse than no caching.

**Observe (falsifier #4 — cross-tab clocks):** the window is stored as a wall-clock timestamp in `localStorage`, shared across tabs. A machine whose clock jumps backwards extends the window; forwards, it expires early. Both are benign here (bounded staleness, extra request) but a design that used the window for anything security-relevant would be wrong.

---

## 5. Make it visible

Any cache design that cannot be observed will be mistrusted, and mistrusted caches get disabled. The site ships a debug panel that logs every object read with its source (`NET` / `CACHE` / `MEM` / `MEMO` / `TTL`), its type, **why it was opened**, its decrypted contents, and a live countdown to the next HEAD check. Open <https://sgit.ai/deploy/>, press **vault panel**, then **clear list**, then click a page: what you see is exactly what that one page needed.

That panel is how the 18-objects-per-page problem in §2 was found in the first place. Recommend shipping the equivalent in any reader — it costs an afternoon and it is the difference between "the cache seems fine" and a measurement.

---

## 6. What this hand-rolls that the CLI already does properly

**This is the actionable part.** The §2 tree walk plus localStorage memo is a client-side re-implementation of something that already exists server-side: the **cache layer** (see `guide__cache-layer-on-live-sg-send-api.md`, 2026-08-13). A declared path gets an encrypted object at a *client-computable* location:

```
cch-pid-{snw|muw}- + HMAC-SHA256(read_key, "sg-vault-v1:file-id:cache-{value|pointer}:{vault_id}:{path}")[:12]
```

A browser holding `vault_id` + `read_key` can compute that id with the same Web Crypto HMAC call it already makes for the ref — no tree walk, no memo, no cold-start cost. Concretely, for the sgit.ai deploy vault:

- **today:** cold visit = 18 requests, because the nav needs every encrypted filename;
- **with `sgit cache add`** on the docs root: the reader resolves a path in one request, and the cold-start cost disappears rather than being amortised.

**Recommendation for the SG/Send team:** run `sgit cache add` against the deployment-docs vault and let the browser reader prefer the cache object, falling back to the tree walk on miss or stale. The fallback path already exists and is exercised; this is additive.

**Recommendations for the CLI/SDK team:**

1. **Ship the browser read path as a supported artifact**, not as something every consumer rediscovers. The derivations, the wire layout, the secure-context requirement and the cache tiers are the same for SG/Vault, for this site, and for any edge function. Two independent implementations already agree on the format — that agreement should be a published test vector set, not folklore.
2. **Make `ref_ttl_s` a first-class notion** in whatever config a reader consumes, with `0` meaning check-every-view. The value is a deployment decision (a docs site wants 120 s; a shared workspace wants 0), and it should not be a constant inside somebody's JavaScript.
3. **Document the read-key-as-published-capability pattern.** It is the most distinctive thing the format enables, and right now it is demonstrated but not specified: what a read key can and cannot do, how to verify a write is refused, and what changes if a deployment flips reads to deny-by-default.
4. **Serial transfer mode for WASM** — already filed; see `brief-serial-transfer-mode-for-wasm.md`. Pyodide cannot spawn threads, so `ThreadPoolExecutor` raises `can't start new thread` mid-clone.
5. **Do not send the access token on `X-API-Key`.** The CLI sends it on both `x-sgraph-access-token` and `X-API-Key`; only the former is allow-listed, and a non-allow-listed header fails the **whole preflight**, so the browser request dies before it is made. Invisible from Python, fatal in a browser. Reproduce:

   ```bash
   for H in x-sgraph-access-token x-api-key; do
     printf '%-24s ' "$H"
     curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS \
       "$EP/api/vault/read/$VAULT/x" -H "Origin: https://sgit.ai" \
       -H 'Access-Control-Request-Method: GET' -H "Access-Control-Request-Headers: $H"
   done
   # x-sgraph-access-token   200
   # x-api-key               400        <- kills the request, not just the header
   ```

---

## 7. Server-change checklist

**None.** Every request in this guide is an ordinary `GET /api/vault/read/{vault_id}/{file_id}`. The only server-side properties relied on are:

- CORS allows the origin and the `x-sgraph-access-token` header (it does; `*` on both `dev.send.sgraph.ai` and `send.sgraph.ai`);
- reads are permitted without a token on that deployment (policy, see §0);
- object bodies are returned verbatim — no transcoding, no compression that changes bytes.

If a future deployment breaks any of those three, the browser reader stops working and the failure will look like a decryption bug. Check them first.
