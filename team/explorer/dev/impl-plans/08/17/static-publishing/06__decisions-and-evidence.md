# 06 — Decisions & Evidence

## 1. Decisions needed from the maintainer

Not the developer agent's to resolve. Each has a recommendation; the build can start on
P1/P3 without any of them.

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| 1 | Canonical layout: `api/vault/read/<vault_id>/…` or flat `bare/…`? | **api-path** | the same URL then works live *and* static; we sniff both anyway, so this only sets what we *emit* |
| 2 | Is the loader always sgit's bundled template, even if the vault contains one? | **Yes** | makes invariant 4 true by construction; a vault copy stays a convenience, never the source |
| 3 | Key file: the key itself, or a pointer to it? | **support both, default to the key** | cross-origin is confirmed working (§2), so a pointer is now a choice; it adds flexibility and a failure mode |
| 4 | Does `serve` bind `127.0.0.1` only by default? | **Yes**, `--bind` to widen, printed loudly | a local convenience should not become an accidental LAN service |
| 5 | Default visibility, and where it is recorded | **bare**, recorded in the vault | a visibility default that drifts is a disclosure, not a preference |
| 6 | Ship P1+P3 before the publish protocol is final? | **Yes** | demonstrable value with zero protocol commitment |

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

## 3. Reproduce it

```bash
python scripts/spike__static_vault_transport.py      # folder + HTTP clones, layout sniffing
python scripts/spike__measure_commit_bundles.py      # bundle economics
curl -sI https://sgit-ai.github.io/SGit-AI__API/ | grep -i access-control
```

Source reviews with the full working: `team/explorer/architect/reviews/08/17/`.
