# CloudFront Direct Blob Serving — Architecture Proposal

**Date:** May 1, 2026

---

## Problem

The current sgit pull/clone download path has two hops:

```
sgit client → FastAPI (validate token, generate presigned URL) → S3
```

For a vault with 1,000 blobs this means FastAPI generates 1,000 presigned S3 URLs (in batches), and every download hits S3 directly from the client's region. Two costs:
- **Latency**: presigned URL generation adds a round-trip per batch before any download starts
- **Cost**: S3 egress (~$0.09/GB) on every pull, even for unchanged blobs that were already downloaded last week

---

## Proposed Architecture

Add a CloudFront distribution in front of the vault S3 bucket. The client fetches blobs directly from CF instead of presigned S3 URLs.

```
sgit client → CF edge node → S3 (via Origin Access Control)
```

FastAPI is no longer in the download path. It is still needed for writes (push, commit) and metadata queries (log, status).

---

## Why Option B: Encryption as the Security Boundary

The blobs stored in S3 are AES-256-GCM encrypted. The vault key is derived client-side from the user's passphrase via PBKDF2 + HKDF-SHA256 and never transmitted to the server. This means:

- **Anyone who downloads a blob gets an unreadable ciphertext** — decryption requires the vault key, which only the client holds
- **Offline brute-force is computationally infeasible**: AES-256-GCM + HKDF-SHA256 + PBKDF2 with a high iteration count makes exhaustive key search impractical
- **The encryption IS the access control** — transport-level access control is defence-in-depth, not the primary security boundary

Given this, the vault's S3 prefix can be made publicly readable via CloudFront. No per-request auth tokens, no presigned URL generation, no Lambda@Edge.

### Accepted tradeoffs

Making blobs publicly accessible via CF leaks some metadata:
- Vault existence (a vault ID maps to a CF path)
- Approximate vault size (blob count)
- Update frequency (new objects appear over time)

This is acceptable because:
1. Vault IDs are random and unguessable (not enumerable)
2. The content — the thing that actually matters — is never exposed
3. The threat model for sgit is content confidentiality, not vault existence confidentiality

---

## What Changes in sgit

### Server side

1. S3 bucket policy: vault data prefix (`/{vault_id}/data/`) accessible by CloudFront OAC only (not public internet directly — CF is the edge)
2. CF distribution: origin = S3 bucket, OAC enabled, cache behaviour set to immutable for CAS objects
3. FastAPI: no longer generates presigned S3 URLs for blobs — returns blob IDs + CF base URL instead

### Client side (sgit pull/clone)

Current flow:
```python
# For each batch of blob IDs:
urls = api.get_presigned_urls(vault_id, blob_ids, token)
for url in urls:
    data = http.get(url)
    store_blob(data)
```

New flow:
```python
cf_base = f"https://cf.sgit.ai/{vault_id}/data"
for blob_id in blob_ids:
    data = http.get(f"{cf_base}/{blob_id}")
    store_blob(data)
```

The presigned URL round-trip disappears. The client constructs URLs directly and fetches in parallel. Simpler client code, better parallelism.

---

## Cache Behaviour

CAS blobs are immutable by design: same content always has the same object ID, and object IDs are content-addressed (SHA-256 of ciphertext). CF can cache them indefinitely:

```
Cache-Control: public, max-age=31536000, immutable
```

On a second clone of the same vault (or a pull that fetches blobs already pulled by other clients), CF serves from the edge cache — zero S3 read cost, edge latency.

Mutable objects (HEAD ref, latest commit pointer) are not cached or have TTL=0.

---

## Estimated Impact

| Metric | Before | After |
|--------|--------|-------|
| Pull latency (cold) | FastAPI RTT + S3 RTT per batch | CF edge RTT per blob (parallel) |
| Pull latency (warm cache) | FastAPI RTT + S3 RTT | CF edge RTT (cache hit) |
| S3 egress cost | Full egress per pull | Only on CF cache miss |
| FastAPI load on pull | Presigned URL generation for every blob batch | Zero — not in read path |
| Clone of popular vault | Full S3 read every time | Near-zero after first client |

---

## S3 Path Structure Required

For CF to map cleanly to vault prefixes, the S3 layout must be:

```
/{vault_id}/data/{object_id}      ← CAS blobs (immutable, long TTL)
/{vault_id}/refs/HEAD             ← mutable, no cache
/{vault_id}/refs/commits/{id}     ← immutable once written
```

CF behaviour rules:
- `/{vault_id}/data/*` → CF origin path `/data/*` with immutable cache policy
- `/{vault_id}/refs/HEAD` → no cache (TTL=0)

---

## Implementation Steps (when ready to build)

1. Create CF distribution with S3 origin + OAC
2. Add CF cache policies: immutable for `/data/*`, no-cache for `/refs/HEAD`
3. Update S3 bucket policy to allow OAC read on vault data prefixes
4. Update FastAPI `pull`/`clone` response to return `cf_base_url` instead of presigned URLs
5. Update sgit client to construct CF URLs directly (remove presigned URL fetch loop)
6. Optional: add `X-Vault-Id` header on CF requests so access logs can be filtered per vault

No changes to the encryption layer, vault format, or commit/tree schema.
