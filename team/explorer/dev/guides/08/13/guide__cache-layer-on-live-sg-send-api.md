# Guide — Using the Cache Layer Against the Live SG/Send API (no server changes)

**Date:** 2026-08-13 · **Audience:** anyone validating the cache layer end to end — and, later, the SG/Vault team, for whom §4 is the reference read implementation
**Server:** `https://send.sgraph.ai` (spec: `https://send.sgraph.ai/api/openapi.json`)
**Claim under test:** the cache layer needs **zero server changes** — every operation is an ordinary vault read/write/delete/list through the existing endpoints. This guide is the executable version of that claim: each step says what to run and what observation would falsify it.

> The cache layer in one sentence: a declared vault path gets a small encrypted object at a **client-computable** location (`bare/cache/value/…` holds a copy of the content; `bare/cache/pointer/…` holds a `blob_id`/`tree_id` locator), maintained by every aware push, so a reader holding `vault_id` + `read_key` resolves that path in **one request** instead of walking the tree.

---

## 0. Prerequisites

```bash
pip install sgit-ai            # or run from a checkout of this repo
export SGIT_BASE_URL=https://send.sgraph.ai
export SGIT_TOKEN=<your SG/Send access token>     # writes require it; ask the SG/Send team
```

All commands pass the server explicitly so nothing here depends on local defaults:

```bash
alias sgit='sgit --base-url $SGIT_BASE_URL --token $SGIT_TOKEN'
```

Endpoints used, all pre-existing (verified against the live OpenAPI spec):

| Endpoint | Cache-layer use |
|---|---|
| `PUT  /api/vault/write/{vault_id}/{file_id}` | publish a cache object (nested file_id) |
| `POST /api/vault/batch/{vault_id}` | reconcile batch (write/delete ops); one-request read (read ops) |
| `GET  /api/vault/list/{vault_id}?prefix=bare/cache/` | discover cache objects (D6 healing, repair) |
| `DELETE /api/vault/delete/{vault_id}/{file_id}` | remove an orphaned cache object |
| `GET  /api/vault/read/{vault_id}/{file_id}` | resolve a blob pointer |

---

## 1. Create a vault with cached paths

```bash
mkdir site && cd site
sgit init .
mkdir -p pages media keys
echo '# Welcome'            > pages/home.md
echo '{"service":"demo"}'   > keys/api.json
echo 'image-bytes'          > media/logo.png
sgit commit "initial"
sgit push

sgit cache add keys/api.json        # small hot record → value cache (auto)
sgit cache add media                # folder → pointer cache (auto)
sgit cache status                   # both listed, both fresh
sgit push                           # publishes the two cache objects
```

**Observe (falsifier #1 — nested file_ids):** the server must accept a `file_id` like `bare/cache/value/cch-pid-snw-XXXXXXXXXXXX`:

```bash
curl -s -H "x-sgraph-access-token: $SGIT_TOKEN" \
  "$SGIT_BASE_URL/api/vault/list/<vault_id>?prefix=bare/cache/"
```

Expected: both cache file_ids listed. If the server rejected nested segments or the prefix filter missed them, **that** would be the server change needed. (The spec types `file_id` as an unconstrained path parameter, so none is expected.)

`<vault_id>` and the ids below come from `sgit vault info` and `sgit cache status --json`.

---

## 2. The maintenance loop (write side)

```bash
echo '{"service":"demo","v":2}' > keys/api.json
sgit commit "rotate key record"
sgit cache status        # keys/api.json now STALE — commit moved the head
sgit push                # reconcile phase rewrites it after content + ref are durable
sgit cache status        # fresh again
```

**Observe (falsifier #2 — batch semantics):** the reconcile is a second batch of plain `write` (and, for removed paths, `delete`) ops issued after the ref-CAS batch. Delete a cached file and push:

```bash
rm keys/api.json
sgit commit "drop key record" && sgit push        # push output: cache_deleted=1
```

The `list?prefix=bare/cache/` call from §1 must no longer show the value object. If batch `delete` ops on nested file_ids failed, that would be a server change — none expected, the CLI already uses the identical op elsewhere.

---

## 3. Cross-clone healing (the D6 property)

```bash
cd .. && sgit clone '<vault-key>' site-b && cd site-b
echo '# Welcome v2' > pages/home.md            # site-b knows NOTHING about caches
sgit commit "edit from clone B"
sgit push                                       # output: cache_updated >= 1
```

Clone B never declared anything, yet its push heals the caches clone A declared — because targets come from the server listing, not local state. **Observe (falsifier #3):** re-run the §1 list call; decrypting the value object (next section) must show B's content. This is the scenario the multi-clone QA suite runs against the in-memory API; here it runs against the real one.

---

## 4. The payoff — one-request read with no clone (the Lambda pattern)

This is the §4.2 capability: `vault_id` + `read_key` (from `sgit vault derive-keys '<vault-key>'`) and nothing else — no working copy, no write capability. This snippet is deliberately runnable *outside* any vault directory:

```python
# read_cached.py — one-request cache read; needs only sgit-ai installed
import sys
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API                 import Vault__API
from sgit_ai.core.actions.cache.Vault__Cache_Reader import Vault__Cache_Reader

base_url, token, vault_id, read_key_hex, path = sys.argv[1:6]
api    = Vault__API(base_url=base_url, access_token=token); api.setup()
reader = Vault__Cache_Reader(crypto=Vault__Crypto(), api=api)

r = reader.read_path(vault_id, bytes.fromhex(read_key_hex), path)
print(f"found={r['found']} fresh={r['fresh']} round_trips={r['round_trips']}")
if r['content'] is not None:
    sys.stdout.buffer.write(r['content'])
elif r['target_id']:
    print(f"pointer -> {r['target_kind']} {r['target_id']}")   # tree: start a walk here
if r['fallback']:
    print("(stale or miss: caller should fall back to the tree walk)", file=sys.stderr)
```

```bash
python read_cached.py $SGIT_BASE_URL "$SGIT_TOKEN" <vault_id> <read_key_hex> keys/api.json
# found=True fresh=True round_trips=1
# {"service":"demo","v":2}
```

Under the hood that single round trip is one batch call — the raw HTTP a non-Python consumer (the SG/Vault browser, an edge function) would make:

```bash
curl -s -X POST "$SGIT_BASE_URL/api/vault/batch/<vault_id>" \
  -H "x-sgraph-access-token: $SGIT_TOKEN" -H 'Content-Type: application/json' \
  -d '{"operations":[
        {"op":"read","file_id":"bare/refs/<ref-pid-muw-...>"},
        {"op":"read","file_id":"bare/cache/value/<cch-pid-snw-...>"},
        {"op":"read","file_id":"bare/cache/value/<cch-pid-muw-...>"},
        {"op":"read","file_id":"bare/cache/pointer/<cch-pid-snw-...>"},
        {"op":"read","file_id":"bare/cache/pointer/<cch-pid-muw-...>"}]}'
# → {"results":[{"file_id":"...","status":"ok","data":"<base64 ciphertext>"}, ...]}
```

The client then AES-GCM-decrypts `data` with `read_key` (wire layout `IV(12)‖ct‖tag(16)`), checks the object's recorded `path` equals the requested path (48-bit collision guard), and compares its `commit_id` to the decrypted ref. Ids are computed locally: `cch-pid-{snw|muw}-` + `HMAC-SHA256(read_key, "sg-vault-v1:file-id:cache-{value|pointer}:{vault_id}:{path}")[:12]` — all four candidates go in the same batch because the mutability label is not part of the hash. Derivation test vectors: contract §4.1 (`tests/unit/crypto/test_Vault__Crypto__Cache_Ids.py`).

**Observe (falsifier #4):** batch `read` ops must return per-file `status`/`data` with `not_found` (not a whole-request error) for absent candidates — the reader depends on partial results. This matches the documented behaviour the CLI already relies on for clone.

---

## 5. Recovery

```bash
sgit cache repair --dry-run     # report drift/orphans/duplicates without changing anything
sgit cache repair               # heal, and publish the fixes
```

Worth knowing while testing: repair (and any aware push) also heals caches that *other* writers left stale — so an "old" sgit or the web UI editing the vault leaves caches stale-but-detectable, never wrong, until the next aware writer runs.

---

## 6. Server-change checklist — the actual answer

| # | Requirement on the server | Expected on `send.sgraph.ai` | If it fails instead |
|---|---|---|---|
| 1 | Accept nested `file_id` (`bare/cache/value/…`) on write/read/delete/batch | ✅ works — `file_id` is an unconstrained path param | route/path-segment handling change |
| 2 | `list?prefix=bare/cache/` returns those file_ids | ✅ works — same mechanism as `bare/refs/` | prefix-filter change |
| 3 | Batch `read` returns per-file `not_found`, not whole-request failure | ✅ works — clone already depends on it | batch handler change |
| 4 | Batch `delete` on nested file_ids | ✅ works — same op the CLI uses today | batch handler change |
| 5 | No server knowledge of cache semantics required | ✅ by design — server stores opaque ciphertext at opaque names | — (would indicate a design leak) |

Anything observed outside the ✅ column is the precise, minimal server change to raise with the SG/Send team. As of the live OpenAPI spec, **the expectation is: no changes** — the server cannot even distinguish a cache object from any other vault file, which is the zero-knowledge property doing its job.

Two client-side limits to be aware of while testing (documented in the post-implementation review, not server issues): value caches are capped at 1 MB (`--pointer` for anything larger), and pointer resolution for >4 MB blobs falls back to the tree walk rather than using presigned reads.

---

*Companion documents: wire-format contract (`team/explorer/architect/contracts/08/12/v0__contract__cache-layer-wire-format.md`), decisions D1–D10 (`v0.3__architecture__cache-layer-decisions.md`), post-implementation review (`team/explorer/architect/reviews/08/13/`). The multi-clone behaviour in §3 is asserted by `tests/qa/test_QA__Scenario_3__Cache_Multi_Clone.py`; the same workflow runs against a real server in `tests/integration/test_Vault__Cache__Integration.py`.*
