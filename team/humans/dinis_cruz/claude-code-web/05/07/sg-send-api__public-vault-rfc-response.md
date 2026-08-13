# Public Vault RFC — SGit-Team Response

**Date:** 2026-05-07
**To:** SG/Send API team (Architect + AppSec)
**From:** SGit team
**Re:** RFC v0.27.5 — Public Vault Type / CDN-Direct Access
**Status:** Constructive feedback + simplifications + concrete asks

---

## TL;DR

Strong support for Public Vault as a feature direction. After review with the project lead, we're proposing a **substantially simpler design** than the RFC outlines:

- **Server-side:** identical to today's vault publishing flow, plus storing the `read_key` as a file at vault-create time, plus routing to a separate public bucket when an explicit flag is set.
- **Sgit-side:** one new field in local config (`public: bool`), propagated to every API request as an HTTP header. **No new transport. No CDN logic in sgit.** ~½ day of work.
- **Phase 1 ships without CloudFront at all.** Reads still flow through FastAPI but hit the public bucket. The bucket-isolation security boundary is the win for Phase 1.
- **Phase 2 adds CloudFront in front of the public bucket with conservative caching** (`Cache-Control: no-cache` everywhere). The latency win comes from skipping the Lambda layer, not from edge caching.
- **Phase 3 is the aggressive-caching optimisation** — only on immutable `bare/data/*` objects; refs and indexes stay no-cache forever (or with origin invalidation on push).

Below: corrections to the storage model the RFC describes, the sgit-side design, the server-side asks, and the phasing.

---

## 1. Corrections to the storage model

The RFC's "How Vaults Work Today" section describes git's layout, not sgit's. The implementation should be designed against the actual sgit structure:

| RFC describes | Sgit actually does |
|---|---|
| Separate `objects/`, `trees/`, `commits/` directories | **Single content-addressed namespace** at `bare/data/obj-cas-imm-*`. Blobs, trees, and commits all live here, distinguished by the encrypted `schema` field (`tree_v1`, `commit_v1`) inside each object. |
| `refs/heads/main` as plaintext branch pointers | **Encrypted ref files** at `bare/refs/<ref-id>`, where ref-id is HKDF-derived from the read-key. Plaintext refs don't exist in sgit. |
| `_write_key` file in bare data on the server | **From sgit's wire perspective:** the client sends the write-key on every write as the header `x-sgraph-vault-write-key`. What the server stores to validate it (the key itself, a hash, an HMAC verifier) is a server-side decision sgit doesn't see. **The AppSec question for public vaults is whether whatever the server stores is safe to expose if the manifest ends up in a public-readable bucket** — see §4.7 Q2. |
| Bare data is the entire picture | Missing: `bare/indexes/<index-id>` — the encrypted **branch index**, which lists all branches in the vault. Required by every clone to discover branch structure. |

The actual layout sgit produces:

```
.sg_vault/                          (client)
├── bare/
│   ├── data/                       (all content-addressed objects: obj-cas-imm-*)
│   ├── refs/                       (encrypted per-branch refs)
│   └── indexes/                    (encrypted branch index file)
└── local/                          (client-only state — never sent to server)
    ├── vault_key                   (the only place the vault key lives)
    ├── config.json
    └── move-history.json           (when applicable)

s3://sg-vaults-private/{deployment}/{vault-id}/   (server)
├── bare/data/                      (matches client)
├── bare/refs/                      (matches client)
├── bare/indexes/                   (matches client)
└── manifest.json                   (server-side: vault_id, write_key_hash, etc.)
```

Two consequences for the public-vault design:

1. **Whatever the server stores to validate the write-key MUST NOT end up in the public bucket as a plaintext credential.** Sgit's wire format only shows the client SENDING the write-key per request (`x-sgraph-vault-write-key`); whatever the server keeps to validate that key (the key itself, a hash, an HMAC verifier) is server-side. For public vaults, the manifest or any equivalent server-side metadata file MUST either (a) live outside the public-readable prefix, or (b) store a one-way verifier (hash / HMAC) such that exposure doesn't enable forged writes. **Please confirm in the §4.7 Q2 reply which of these you currently do and which you'll do for public vaults.**

2. **The branch index must also be public-readable** — every sgit clone derives the index file_id from the read_key and fetches it during clone. Without `bare/indexes/<index-id>` accessible, no client can discover the vault's branch structure. Confirm the public bucket's read policy covers the entire `bare/` prefix, not just `bare/data/`.

---

## 2. The simplified design

Three clarifications from the project lead that drop the implementation complexity by ~70%:

### 2a. Server-side: identical to today, plus one stored file

The publishing flow does not need a parallel code path. Every existing operation (create, push, batch_write, batch_read) works unchanged. The only differences are:

- **At vault create time, when the public flag is set:** store the `read_key` as a file at the vault prefix (e.g. `bare/_read_key` — exact path is the API team's call).
- **Bucket routing:** when the request includes `X-Vault-Public: true` (or equivalent), route to `sg-vaults-public` instead of `sg-vaults-private`. Public-flagged vaults always live in the public bucket; private vaults always live in the private bucket. No mixing.

Everything else — write authentication, manifest management, batch operations, ref updates, content-addressing — is unchanged. The public bucket happens to be world-readable; that's the only structural difference.

### 2b. Sgit-side: one flag, one header, no new code paths

Sgit needs three small changes and nothing else:

```python
# 1. Schema__Local_Config gains one field
class Schema__Local_Config(Type_Safe):
    ...
    public : bool = False                 # NEW

# 2. Vault__API attaches one header per request
def _make_request(self, ...):
    headers = {...}
    if self.public:
        headers['X-Vault-Public'] = 'true'
    ...

# 3. CLI flags wire it in at init/clone
sgit init --public                        # sets public=True in local config
sgit clone <key> --public                 # sends header on first request
```

After init/clone, the flag is persisted in `.sg_vault/local/config.json` and every subsequent request automatically includes the header. No user awareness of public-vs-private after the first command. No new transport, no CDN integration, no separate read/write paths in sgit.

This mirrors how `--token` works today: set once, sgit propagates it on every request automatically.

### 2c. Caching: defer the hard part

CDN caching of mutable refs is genuinely hard (refs change on every commit; aggressive caching = stale heads after push). **We don't need to solve it for v1.**

The latency win for Public Vault comes from **skipping the Lambda layer**, not from edge caching. Today's flow:

```
Client → API Gateway → Lambda (cold ~200ms / warm ~30ms) → S3 → Lambda → Client
```

Phase 2 with CloudFront and `Cache-Control: no-cache` everywhere:

```
Client → CloudFront edge → S3 (~50ms uncached) → Client
```

The Lambda layer was the slow part. Even fully uncached CDN reads will be measurably faster. Aggressive caching on immutable `bare/data/*` is the Phase 3 optimisation; refs can stay no-cache forever and the design still works.

---

## 3. What sgit will implement

When the server side is ready (or in lockstep with it), the sgit-side change is:

1. **Add `public: bool` to `Schema__Local_Config`** (Type_Safe round-trip enforced; defaults `False`).
2. **Plumb the flag through `Vault__API`** so every outgoing request carries `X-Vault-Public: true` when set.
3. **CLI flags:**
   - `sgit init --public` → writes `public: True` into the new vault's local config; the first push includes the header so the server creates the vault in `sg-vaults-public`.
   - `sgit clone <vault-key> --public` → first request includes the header; the API responds with the public-vault data; sgit writes `public: True` into the cloned local config.
   - `sgit vault config public {true|false}` → toggle the flag (rare; mostly set at create/clone time).
4. **Auto-detection on clone:** the API response should include a `public: true` field in the vault manifest so sgit can persist the flag without the user re-passing it. (Server change, see §4 below.)
5. **Tests:**
   - Round-trip the flag through Schema__Local_Config.
   - Confirm the header is attached when `public=True` and absent when `public=False`.
   - End-to-end: init with `--public`, push, clone with `--public`, assert the cloned config has `public: true`.
   - Auto-detection: clone WITHOUT the flag against a known public vault — confirm the response surfaces the flag and sgit persists it.

Total sgit-side surface: ~6-8 unit tests, ~½ day of dev work. Slots into the brief pack as a follow-up brief after the visualisation track lands.

---

## 4. What we're asking the API team to do

Numbered for easy reference in your reply.

### 4.1. Bucket setup

Create `sg-vaults-public` with the same path structure as `sg-vaults-private` (`{deployment}/{vault-id}/bare/...`). Configure for public read on the entire `bare/` prefix (data, refs, indexes — all of them). Private bucket stays untouched.

### 4.2. Header recognition + routing

Recognise `X-Vault-Public: true` (or whatever name you prefer — let us know and we'll match it) on every vault API endpoint. When set:
- Route reads/writes to `sg-vaults-public`.
- When absent or `false`, route to `sg-vaults-private` (current behaviour).

Reject mixed states explicitly — if a vault_id exists in the public bucket and a request arrives without the flag (or vice versa), return a clear error rather than 404 or "vault not found".

### 4.3. Read-key storage at create time

When `vault create` is called with the public flag set:
- Generate the vault_key as today (or accept a user-supplied one).
- Compute the read_key from it as today.
- **Additionally** store the read_key as a file in the public bucket at the vault prefix. Suggested path: `bare/_read_key` (or whatever fits your conventions). Plain bytes — no encryption needed since it's the decryption key.
- Store the `_public` marker file too (per the RFC's design).

For private vaults: no change. Read-key stays only on the client (derived from the vault_key).

### 4.4. Manifest exposure of the `public` flag

Add `public: true` to the public-vault manifest's response. This lets sgit auto-detect on clone whether it's looking at a public vault, so users don't have to remember to pass `--public` on every clone — the first response tells sgit, and sgit persists the flag in local config.

### 4.5. No CDN required for Phase 1

Phase 1 = bucket isolation + header routing + read-key storage. Reads continue through FastAPI; the difference is they target the public bucket. This already delivers the data-isolation security guarantee (impossible to misconfigure private data into a public bucket).

### 4.6. CDN configuration for Phase 2

CloudFront distribution in front of `sg-vaults-public` only. Conservative caching:

- All paths: `Cache-Control: no-cache, must-revalidate` initially.
- Once Phase 2 ships and is stable, Phase 3 differentiates:
  - `bare/data/obj-cas-imm-*` → `Cache-Control: public, immutable, max-age=31536000` (content-addressed, immutable forever, safe to cache aggressively).
  - `bare/refs/*` → stay `no-cache` (mutable; changes on every commit).
  - `bare/indexes/*` → stay `no-cache` (mutable; changes on branch add/remove).

CORS configuration: allow GET from any origin (the public vault is meant to be readable by browsers and CLIs alike).

### 4.7. AppSec considerations

The RFC asks the right questions in §"Questions for the AppSec Agent". Consolidated responses with the simplified design:

- **Q1 (read-key derivation safety):** The read_key cannot derive the vault_key (HKDF is one-way). It cannot derive the write_key (different HKDF context). Possession of the read_key + bare data does not enable any write operation **provided the server's write-validation material is not exposed** — see Q2.
- **Q2 (write-key handling for public vaults — REAL QUESTION, NOT DISMISSED):** Sgit only sees the wire side: the client sends `x-sgraph-vault-write-key: <write_key>` on every write. Whatever the server stores to validate that key is a server-side decision — likely some combination of the manifest, KMS, or a separate auth store. For public vaults: **what does the server store, and where?** Three sub-questions:
  - If the verifier is in a per-vault manifest file (`manifest.json` or equivalent), and that file lives at the vault prefix in the public bucket, is it accessible to anyone with the URL? If yes, what does it contain? If it's the plaintext `write_key`, that's a write-credential exposure and Public Vault is unsafe as designed.
  - If the verifier is a hash / HMAC of the write_key, exposure is benign — the server compares hash-of-incoming-key to the stored hash; an attacker with the hash cannot reverse it to forge a valid `x-sgraph-vault-write-key` header.
  - Recommended posture for public vaults: ensure the server stores a one-way verifier (hash or HMAC) so manifest exposure doesn't enable forgery. If today the server stores the plaintext write_key, public vaults need a manifest format change (or to keep the manifest in a private prefix outside the public-readable area).
- **Q3 (CDN cache poisoning):** Content-addressed objects (`obj-cas-imm-*`) are tamper-evident — clients can verify by re-hashing. Refs are encrypted, so a poisoned ref would fail to decrypt under the read_key. Worth recommending client-side hash verification on objects (cheap, ~10ms per object) — sgit can opt in.
- **Q4 (client-side hash verification):** Yes for `bare/data/*` (cheap; defeats poisoning). No for refs (encryption + decrypt-failure already detects tampering). Sgit can implement this on the read path.
- **Q5 (metadata leakage):** A public vault's metadata (object count, sizes, commit graph shape) is necessarily exposed. If a vault owner doesn't want this, the answer is "don't make the vault public" — there's no half-state.
- **Q6 (separate-bucket boundary):** Yes, this is the right boundary. Add CloudWatch logging on the public bucket; alert on any non-API write attempt; nothing outside the API should ever PUT into the bucket.

### 4.8. Takedown / unpublish

The RFC doesn't address this and it matters. Once content is served from a public bucket, especially with any CDN caching, **it's effectively in the wild** — scrapers, cached copies, etc. Recommendation:

- Surface a `vault unpublish` API call that wipes the bucket prefix (and CloudFront-invalidates if Phase 2+).
- The user-facing message must say: "unpublishing removes the vault from the bucket, but already-served copies cannot be revoked."
- Don't pretend takedown is reversible.

This is policy as much as engineering. AppSec should confirm whether this is acceptable given the use case, or whether there's a stricter requirement (no public vaults at all, public-only-with-explicit-licence-acknowledgement, etc.).

---

## 5. Phasing

| Phase | Server | Sgit | Latency win | Estimated work |
|---|---|---|---|---|
| 1 | Bucket + header routing + read-key storage | Local config field + header propagation + CLI flag | None (still through FastAPI), but data-isolation security boundary in place | API: ~1-2 days. Sgit: ~½ day. |
| 2 | CloudFront in front of public bucket; `Cache-Control: no-cache` everywhere | Optional read-from-CDN-URL transport (sgit detects manifest CDN URL, prefers it for reads) | Significant — Lambda layer skipped | API: ~1 day. Sgit: ~1 day if read-from-CDN is added; 0 if API stays the read path. |
| 3 | Aggressive caching on `bare/data/*` only; invalidation-on-push for refs/indexes if needed | None | Marginal further; mostly cost reduction | API: ~½ day. |

**Phase 1 ships value standalone** even without Phase 2. The bucket separation is the security guarantee; the latency improvement is a nice-to-have that arrives in Phase 2.

---

## 6. What we're asking back from you

1. **Bucket + header design check.** Are the proposed bucket name, header name, and read-key storage path consistent with your conventions? Tell us the names you prefer and we'll match.
2. **Manifest exposure of the public flag.** Confirm you can add `public: true` to the manifest response so sgit can auto-detect on clone.
3. **Write-key verifier format (the AppSec gating question).** What does the server currently store to validate the `x-sgraph-vault-write-key` header? If it's the plaintext write_key in a per-vault manifest, and that manifest sits in the public bucket prefix, public vaults are unsafe as designed and need either (a) the manifest moved out of the public-readable prefix, or (b) the verifier changed to a one-way hash / HMAC. **This is the key blocker** — the answer determines whether Phase 1 can ship at all.
4. **Phase 1 scope estimate.** Once Q3 is resolved, is "bucket + header routing + read-key storage + (any manifest changes)" something you can land in ~1-2 days, or are there infra hurdles we haven't seen?
5. **AppSec sign-off.** Specifically on the takedown/unpublish question (§4.8) and the bucket-as-security-boundary approach (§4.7 Q6).
6. **Phase 2 timing.** When you're ready to add CloudFront, we'll add the optional read-from-CDN transport on the sgit side. Until then, sgit just sets the flag and reads through FastAPI.

If anything in §1's storage corrections changes your design assumptions, please flag — the API team's design needs to be against the actual sgit structure, not the git-style structure the RFC implied.

---

## Out of scope for this round

- Changing how Simple Tokens are derived. Public vaults work with both Simple Tokens (`word-word-NNNN`) and full vault keys (`<passphrase>:<vault_id>`).
- Per-branch publication. v1 = whole vault is public OR private. Per-branch visibility is a v2 feature if there's demand.
- Public-vault migration tooling. v1 doesn't migrate existing private vaults to public; users create vaults explicitly public from day one. (When `vault move` lands, the move workflow could optionally include "and switch to public" — future enhancement.)
- Web-client integration. The SG/Send web client (`createFromToken`) reading public vaults directly from CloudFront is a natural extension but lives in a separate workstream once the bucket is publicly readable.

---

## Sgit-team contact

Replies to this document can land in the v0.14.x brief pack at `team/villager/v0.14.x__brief-pack/`, or as a direct response in your usual channel. We'll queue the sgit-side implementation as a follow-up brief once you confirm Phase 1 scope.

This document is released under the Creative Commons Attribution 4.0 International licence (CC BY 4.0) — same as the original RFC.
