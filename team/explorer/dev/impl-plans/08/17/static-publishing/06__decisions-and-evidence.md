# 06 — Decisions & Evidence

## 1. Decisions needed from the maintainer

Not the developer agent's to resolve. Each has a recommendation; the build can start on
P1/P3 without any of them.

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| 1 | Canonical layout: `api/vault/read/<vault_id>/…` or flat `bare/…`? | **api-path** | the same URL then works live *and* static; we sniff both anyway, so this only sets what we *emit* |
| 2 | Is the loader always sgit's bundled template, even if the vault contains one? | **Yes for what `publish` emits** — a vault's own `index.html` is ciphertext then. It takes precedence only at **deployment-time expansion**, where it simply replaces the loader *(settled 19 Aug)* | keeps I4 unconditional and keeps vault content out of the publish output entirely |
| 3 | Key file: the key itself, or a pointer to it? | **support both, default to the key** | cross-origin is confirmed working (§2), so a pointer is now a choice; it adds flexibility and a failure mode |
| 4 | Does `serve` bind `127.0.0.1` only by default? | **Yes**, `--bind` to widen, printed loudly | a local convenience should not become an accidental LAN service |
| 5 | Default visibility, and where it is recorded | **bare**, recorded in **per-clone local config** (`.sg_vault/local/config.json`) — *revised* | if visibility travelled inside the vault, a cloner running `publish` would disclose the read key by inheriting config they never chose |
| 6 | Ship P1+P3 before the publish protocol is final? | **Yes** | demonstrable value with zero protocol commitment |
| 7 | Swagger UI delivery: CDN+SRI, or vendored into the published folder? | **CDN+SRI is the default**; `--api-docs=bundled` is the opt-in — *revised, see §2.8* | the UI is 1.53 MB, ~2.7× the whole vault; SRI closes the security objection that first argued for vendoring |
| 8 | Emit `api/openapi.json` always, or only with `--api-docs`? | **with `--api-docs` now; consider always once soaked** | it is a few KB and makes a published vault self-describing to an agent |
| 9 | Output target for `sgit publish` | **none — it always writes `.sg_vault/publish/`, and nothing else changes** *(settled 19 Aug)* | removes the question rather than policing it: no containment rule, no `--force` hazard, no new tracked folder to collide, and the amplification loop is impossible by construction (`07`) |
| 10 | Build `static.sgit.ai` as a first-party asset origin? | **Yes — S3/CloudFront, not Pages; publish-time source only, never on a reader's critical path** | Pages stamps `max-age=600` and cannot serve immutable assets; a read-time first-party origin would make us the beacon every vault reader pings (`09`) |
| 11 | Where does plaintext expansion live? | **`sgit vault expand` (P8), deferred — removed from `publish` entirely** *(settled 19 Aug: R1)* | `publish` emitting vault content contradicted `07` §3; until P8, the one-folder git pattern's committed work tree *is* the expanded deployment (`10`) |

## 2. Evidence base — what we measured, and what it changed

Everything here is reproducible from the scripts named at the end.

### 2.1 GitHub Pages permits cross-origin reads — test cell 10 is supported

The source brief assumes a pages host "is not configurable at all" and treats
key-on-another-origin as probably unavailable.

```console
$ curl -sI https://sgit-ai.github.io/SGit-AI__API/
HTTP/2 200
access-control-allow-origin: *          # present by default, and with an Origin header too
```

**Changed:** cell 10 moves from "document as unavailable" to "supported, and asserted at run
time so a platform change fails the suite". The key-file-as-pointer indirection becomes an
option rather than a workaround.

### 2.2 Custody without access requires a manifest — structural, not a gap

Every filename in a vault is `HMAC(read_key, …)` (refs, indexes, caches) or a content hash
learned by decrypting a tree. **With zero key material a client cannot name a single file.**

| Custody route | Works? |
|---|---|
| `git clone` / folder copy / zip of a published target | ✅ the filesystem is the listing |
| `sgit vault mirror` with a published `manifest.json` | ✅ the manifest is the listing |
| `sgit vault mirror` with a host directory listing | ⚠️ where offered |
| `sgit clone <url>` with no key | ❌ **impossible** |

**Changed:** `manifest.json` promoted from optimisation to required; test cell 11 re-scoped
from "bare clone" to "mirror", with the no-manifest failure as part of the test.

### 2.3 Object ids are keyed in effect — a fork is unlinkable

The publish-protocol brief hypothesises that content-addressed ids are hashes over
*plaintext*, so they would survive a rekey and make a private fork of a public template
detectable. Measured, the hypothesis does not hold: ids are `sha256(**ciphertext**)[:12]`,
and blob encryption uses a **random IV**.

| Test | Result |
|---|---|
| two different vaults holding the **same document** | **zero shared object ids** |
| the same content added twice **within one vault** | **not deduped** |
| object ids surviving a **rekey** | **0 of 8** |

**Changed:** no protocol change needed; the publish brief's key claim 12 should be struck.
**Corollary to record:** template-diffing by identifier is impossible — the property that
protects a private fork also prevents cheap "what did this fork change?".

### 2.4 A rekey is a new deployment, and git-hosted publication is irreversible

- A rekey changes the vault_id **and every object id**, so a fork/rotation republishes
  everything at new paths — never a delta.
- On a git-hosted target, deleting old objects leaves them in history, clonable by anyone.
  So a public-repo static vault **cannot revoke read access even with the write key**.

**Changed:** the `--visibility public` confirmation and the git-history note in
`02__commands-and-ux.md` exist because of this. Publish to object storage when revocation
may be needed.

### 2.5 The read path has four server dependencies, not one

| Method | Call sites | Static implication |
|---|---|---|
| `batch_read` | 13 | GET fan-out |
| `presigned_read_url` | 5 | **on the clone path** for >4 MB blobs — must be implemented |
| `read` | 4 | trivially a GET |
| `list_files` | 1 | only in fail-soft cache repair |

**Changed:** P1's acceptance requires a >4 MB fixture. A static transport that only reroutes
`batch_read` passes every small-fixture test and fails on the first real vault with a big
file.

### 2.6 Bundle economics (P6)

A full clone fetches ~99% of all objects; objects are tiny (median 530 B–2 KB); whole vaults
are well under 1 MB. **Request count dominates; bytes are noise.**

```
full store          576 KB / 292 objects
head snapshot       236 KB / 209 objects     <- 41%: all a "latest only" reader needs
incremental pull    172 KB (2 GETs, rest cached forever)   vs 576 KB for a single full pack
zip DEFLATE         1.078× raw at ~10× CPU   vs STORE 1.075×   <- ciphertext is incompressible
```

**Changed:** bundles are per-commit **deltas** plus a head snapshot, `ZIP_STORED`, immutable
names — and `manifest.json` must carry the ordered commit list or bundle fetches serialise.

### 2.7 Static clone already works

Verified against the live deployment — GitHub Pages, no server, no auth, read key only:

```
derived ref file_id : ref-pid-muw-1995ccf51fe8
layout auto-sniffed : api/vault/read/{vault_id}/{file_id}
CLONED              : README.md, app.json, content.json, index.html
```

Also verified from a plain `python -m http.server` and from an unpacked folder with no
network at all. **Changed:** the API repo's pinned `test__cli_clone_stops_at_batch`
good-failure test can flip.

### 2.8 Swagger UI is 2.7× the vault it documents — decision 7 reversed

Measured on `swagger-ui-dist@5.17.14` (raw bytes, and the SRI hashes both delivery modes use):

```
swagger-ui-bundle.js             1,452,753   sha384-wmyclcVGX/WhUkdkATwhaK1X1JtiNrr2EoYJ+diV3vj4v6OC5yCeSu+yW13SYJep
swagger-ui.css                     152,071   sha384-wxLW6kwyHktdDGr6Pv1zgm/VGJh99lfUbzSn6HNHBENZlCN7W602k9VkGdxuFvPn
swagger-ui-standalone-preset.js    230,293   (not needed — topbar/URL explorer only)
                                 ---------
minimum viable docs page         1,604,824   = 1.53 MB   vs a measured full vault of 576 KB
```

**Changed:** the first recommendation (vendor by default) is withdrawn. SRI plus an exact
version pin *closes* the compromised-CDN path — the browser will not execute mismatched
bytes — so the security argument no longer selects vendoring, and the size argument selects
against it: 1.53 MB in every copy, zip and custody mirror of a folder whose payload is
smaller than that. `=bundled` remains for offline, air-gapped and no-third-parties
deployments, and fetches against the same hashes. Full reasoning: `08` §2.2 and §4.

### 2.9 Publishing into the work tree is an amplification loop

`sgit push` skips only what `Vault__Ignore` declares. A published folder inside the work tree
is ordinary content, so publish → push → publish **doubles the store on every cycle**,
silently; and a `--force` publish to an *ancestor* directory would clear `.sg_vault` itself.

**Changed:** the output-target rule (`07__publish-target.md`) became a **P2 blocker** rather
than a UX nicety, every mockup in `02` moved off `./site`, and the no-argument default became
`.sg_vault/publish/` — verified to be already ignored everywhere, and verified *not* to be
swept into backup zips (`Vault__Backup` archives `bare/` plus three named `local/` files).

### 2.10 GitHub Pages cannot host immutable assets — and `static.sgraph.ai` already can

Probed 2026-08-19, which settles where a first-party asset origin would live:

```console
$ curl -sI https://sgit.ai/            → server: GitHub.com   cache-control: max-age=600
$ curl -sI https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css
                                       → cache-control: public, max-age=31536000, immutable
$ curl -sI https://static.sgraph.ai/index.html
                                       → 200, server: AmazonS3, x-amz-bucket-region: eu-west-2,
                                              via: … (CloudFront)          # already deployed
$ curl -sI https://static.sgit.ai/     → does not resolve
```

**Changed:** the `static.sgit.ai` proposal is answered as "yes, on S3/CloudFront, as a
publish-time source only" rather than "yes, on Pages, as a CDN". Pages' 10-minute cache is
not configurable, so a 1.53 MB asset would be re-fetched ~150× more often than on a real CDN
— into a documented 100 GB/month soft cap. Full reasoning, including why a first-party
*read-time* origin is the wrong trade for a zero-knowledge product, in
[`09__asset-origin.md`](09__asset-origin.md).

### 2.11 The executed tabletop — seven claims confirmed, one bug found (19 Aug)

The whole one-repo GitHub Pages flow ran for real (`10__tabletop__github-pages-one-repo.md`):
I6 (publish→push = "Nothing to push"), git dedupes all ciphertext projection copies
(46 files → 29 blobs), static clone on both layouts, keyless custody from the manifest,
the update cycle, **a repo committing `.sg_vault/bare` is already statically clonable**,
and **publish needs only the read key** (commit walk ran from the committed
`sgit_public_read_*` filename). Bug found: a refused `sgit push` rewrites mutable ref
bytes (fresh IV, same commit id) — spurious git dirty state; fix + regression test owed.
Full findings: `team/explorer/architect/reviews/08/19/v1__review__static-publishing-full-pass.md`.

## 3. Reproduce it

```bash
python scripts/spike__static_vault_transport.py      # folder + HTTP clones, layout sniffing
python scripts/spike__measure_commit_bundles.py      # bundle economics
curl -sI https://sgit-ai.github.io/SGit-AI__API/ | grep -i access-control

# §2.8 — sizes and SRI pins (recompute on every version bump, never copy from a web page)
for f in swagger-ui-bundle.js swagger-ui.css swagger-ui-standalone-preset.js; do
  curl -sL -o "$f" "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/$f"
  printf '%-34s %9d  sha384-%s\n' "$f" "$(wc -c < "$f")" \
         "$(openssl dgst -sha384 -binary "$f" | openssl base64 -A)"
done
```

Source reviews with the full working: `team/explorer/architect/reviews/08/17/`.
