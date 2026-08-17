# CLI-Team Response — "Static Clone: A GET Is Open A File, A Folder Is A Remote"

**Responding to:** v0.1.2 proposal, SGit API team, 17 Aug 2026
**From:** sgit CLI team (Architect/Dev) · **Date:** 2026-08-17
**Position:** **Support — and it is smaller than the proposal assumes.** We built a
sizing spike rather than argue from reading: acceptance criteria **#2 and #3 already
pass**, against your reference-shaped bytes AND a real vault, with **zero changes to
any CLI call site**. Three evidence-table corrections below, one of which will break
a naive implementation if not designed for.

Runnable proof in this repo: `scripts/spike__static_vault_transport.py`.

---

## 1. The reframe is right, and the code agrees

"A GET of a computed path and an `open()` of a computed path are the same operation"
is exactly correct for this protocol. The read path never asks the server a
question; it asks storage for bytes at a client-computed name. We verified the whole
chain end to end.

**Proof, on the real vault you supplied (`4bshby5n`, read key only, no server):**

```
derived ref_file_id  = ref-pid-muw-11ea50e81f4d   == the file on disk   ✅
derived idx_file_id  = idx-pid-muw-393a7b9bf7cc   == the file on disk   ✅

A) clone_read_only from an unpacked FOLDER, no network at all  -> OK
   recovered: README.md, app.json, content.json, index.html
B) same bytes behind `python -m http.server`                   -> OK (identical tree)
```

Both static layouts work and are **auto-detected**, not configured:

```
HTTP clone [plain dir server     ] -> OK  (sniffed layout: {file_id})
HTTP clone [live-API path layout ] -> OK  (sniffed layout: api/vault/read/{vid}/{file_id})
FOLDER clone [no network]         -> OK  (sniffed layout: {file_id})
```

## 2. Evidence-table corrections (three)

### C1 — "the batch endpoint is the CLI's only read-path server dependency" — **not accurate, and this one bites**

The read path (clone/pull/fetch/sparse/cache) calls **four** API methods:

| Method | Call sites | Static implication |
|---|---|---|
| `batch_read` | 13 | the fan-out you described |
| `presigned_read_url` | 5 | **on the clone path** — `Vault__Sync__Clone.py:249,336` |
| `read` | 4 | trivially a GET |
| `list_files` | 1 | only in **fail-soft** cache repair — clone/pull unaffected |

`presigned_read_url` is used for every blob flagged `large` (>4 MB) during clone.
A static mode that only reroutes `batch_read` will clone small vaults fine and then
fail on the first vault containing a big file — a nasty, size-dependent bug.

**The fix is free**, which is why it must be designed in now rather than patched
later: the caller does `urlopen(url_info['url'])`, and `urlopen` handles `file://`.
So the static transport returns the object's own direct location as the "presigned"
URL and the existing large-blob code path works unmodified. Our spike does this in
3 lines.

Accurate restatement for your table: *batch is the only server dependency for
cloning small-object vaults; large blobs also require presigned reads, and both
collapse to plain GETs statically.*

### C2 — `Vault__Backend__Local` exists and is unwired: **confirmed — but it cannot be wired "as-is"**

Your Q1 sub-question asks whether it gets wired as-is or re-reviewed first. It must
be re-reviewed: **the `Vault__Backend` interface has no read-batching at all.**
`read/write/delete/list_files/batch` — and the default `batch()` handles only
`write`/`write-if-match`/`delete` ops. It never had a read op. The interface is
write-oriented; the read path's actual workhorses (`batch_read`, presigned reads)
are absent from it.

So Option B is not "wire the shipped class" — it is "extend the interface, then port
every read call site". Real work, and none of it needed to ship static clone.

### C3 — "`sgit_rk1_<hex>:<id>` is not parsed by `clone`" — **outdated; already shipped**

Correct against v0.15.0, fixed since. `sgit clone sgit_rk1_<hex>:<vault_id>` works
in **v0.15.5** (released), alongside the bare `<hex>:<vault_id>` shorthand and
`--read-key`. There is also an explicit precedence rule: `sgit_vk1_` suppresses the
64-hex read-key heuristic, so a genuine 64-hex passphrase can't be misrouted.
**Your Q7 needs no work — just re-test on ≥0.15.5.**

One caveat for your published pages: sgit deliberately still embeds the **bare** key
in `vault.sgraph.ai/...#key` URLs until SG/Vault web strips prefixes on input.

## 3. Answers to the numbered questions

**Q1 — Option A, B, or C?** **Neither A nor B as written: "Option A′ — a sibling
class, injected."** Not a `static=true` flag inside `Vault__API` (your accretion
risk is real), and not the `Vault__Backend` port (C2: bigger than it looks). Instead
a `Vault__API__Static(Vault__API)` overriding the four read methods, constructed at
the CLI boundary and injected exactly like `Vault__API__In_Memory` already is.

Evidence it is the right size: our spike is **~90 lines** and required **zero
changes** to clone, pull, fetch, sparse or cache code. The seam already exists —
every action takes `api=` — which is why the browser could make this move and why we
can too. Option B stays the long-term direction; do it when a third backend earns it,
not as a precondition. Option C (packs) — agreed, defer, but see §4: your own publish
step makes a *simpler* artifact worth more than packs.

**Q2 — concurrency and retries.** Spike used 8 for HTTP, 1 for local (a local fan-out
is pure overhead). Our measurements say request *count* dominates, not bandwidth, so
the useful knob is connection reuse more than raw parallelism — a `Session` with
HTTP/2 or keep-alive beats a bigger pool. Recommendation: default 8, configurable,
**1 for local paths**, retry idempotent GETs twice with backoff, and treat 404 as an
answer (absent) rather than an error — the read path already distinguishes those via
`Schema__Fetch_Failure`. Web team's numbers welcome.

**Q3 — explicit flag, auto-detect, or probe-hint?** The maintainer's requirement is
that this work **transparently** against any GET-able server or folder, so:
**auto-detect, but never silent.** Detection is cheap and unambiguous where it
matters:
- a `base_url` that is not `http(s)://` is a filesystem path → local transport, no ambiguity;
- an `http(s)` origin → try batch once; on 404/405/501/CORS-fail, fall back to GET
  fan-out and remember;
- on-host layout sniffed on the first read (both candidates tried, then sticky).

The honesty requirement is met by **reporting** the resolved transport in the command
output and in `sgit vault info` (`transport: static-http (GET fan-out, read-only)`),
plus `--transport auto|api|static|local` to force it. Visible ≠ silent; that
addresses the "hides deployment mistakes" tension without making users configure what
we can detect.

**Q4 — what is "the read surface"?** From our side, exactly four operations, and we
suggest the contract be defined as *what a clone provably needs*: `GET
/api/vault/read/{vault_id}/{file_id}` (the whole surface, really), plus optionally
`GET /api/vault/list/{vault_id}` where the host can serve it, and the presigned-read
operation marked **not applicable** on static (objects are directly addressable). If
the generated document says "read is one GET", the CLI's four methods all collapse
into it — which is a nice proof of the design's simplicity.

**Q5 — where does generation run?** Your Pages workflow, not `sgit`. Generating the
OpenAPI subset requires the live service's schema, which the CLI does not have and
should not vendor. We agree strongly with your own tension note: **generated or
rejected** — a handwritten contract would drift into a lie. sgit's publish step
should emit the *data* artifacts (§4); the API repo emits the *contract*.

**Q6 — does static clone verify more aggressively?** **It can, for free, and we
recommend making it unconditional on every transport.** Object ids are
`obj-cas-imm-{sha256(ciphertext)[:12]}` — content-addressed over the *ciphertext*.
So the client can hash whatever bytes arrived and compare to the id it asked for,
with no key, no server, and no trust in the host. That is a genuinely stronger
integrity story than the live API offers today (where nothing checks it), and it
matters more when the host is a CDN or a USB stick. Cost: one sha256 per object over
data already in memory. Refs/indexes/caches are not content-addressed, so they stay
authenticated by AES-GCM as today.

**Q7 — the `sgit_rk1_` fix.** Already shipped (C3). Nothing to fold in.

**Q8 — does `sgit remote add` accept folder paths?** Yes, and it should — a folder is
a read-only remote, which is exactly what a networked/mounted share is. Constraint:
remotes must carry their transport and read-only-ness, so `push` to a folder remote
fails at *configuration* time with a clear message, not mid-push. Our spike makes
writes structurally impossible (`write/delete/batch` raise), which is the property we
want to keep.

## 4. Publish-side performance: mapped carefully (the maintainer's ask)

We control what goes into the static folder, so we can add artifacts that remove
requests. **Measured first**, on synthetic vaults plus the real `4bshby5n`:

| Vault | objects published | GETs to clone | bytes fetched | median object |
|---|---|---|---|---|
| real `4bshby5n` | 13 in `bare/` | 13 | ~15 KB | 419 B |
| 20 files / 2 commits | 57 | 54 | 30 KB | 530 B |
| 100 files / 5 commits | 176 | 173 | 324 KB | 2.0 KB |
| 200 files / 10 commits | 341 | 338 | 587 KB | 832 B |

Two facts fall out, and they determine the whole design:

1. **A full clone fetches ~99% of all objects** (338 of 341). There is no clever
   subset to fetch — a full clone genuinely wants everything.
2. **Objects are tiny** (median 530 B–2 KB; 85–100% under 4 KB) and the whole vault is
   well under a megabyte. So **request count dominates completely; bytes are noise.**

That means the highest-value publish artifact is not a clever index — it is simply
*fewer requests*:

| Artifact | Cost | Benefit | Risk |
|---|---|---|---|
| **`bare/packs/<head-commit>.pack` + `.idx`** — every object reachable from a head, concatenated | one extra file per publish, ~= vault size | **N requests → 2** (338 → 2 in the table above). Keyed by commit ⇒ immutable ⇒ infinite CDN TTL | must stay *derived* (see rules) |
| **`bare/manifest.json`** — file_id → size for everything published | tiny | restores `list_files` semantics on hosts that have no listing (fsck, cache repair, planning); lets the client know sizes before fetching | must be regenerated on every publish or it lies |
| **HTTP Range reads against the pack** | none (Pages and S3 both support `Range`) | sparse clone / single-file `cat` fetch only their slice: 2 GETs, no tree walk | index must carry (offset, length) |
| **Cache objects (`bare/cache/*`) — already shipped** | already exists | a declared hot path reads in **one batch** with no clone: verified working over the static folder transport (`found=True, fresh=True`) | none; composes for free |

**Rules that must hold for any of these (learned the hard way from the cache layer):**

- **Derived, never authoritative.** Loose objects remain the source of truth. A
  missing, stale or corrupt pack must degrade to "slower", never to "wrong". Every
  reader falls back to loose GETs. This is the same rule as cache-layer D10, and the
  reason our cache work survived four rounds of review.
- **Immutable naming.** Pack keyed by head commit (`<commit-id>.pack`), never
  `latest.pack` — a mutable name fights CDN caching and races a publish in progress.
  The **ref stays loose and tiny**: it is the only mutable object, so freshness is one
  small GET that can be cache-busted independently.
- **Verifiable without trust.** Because ids are `sha256(ciphertext)[:12]`, every
  object extracted from a pack is checkable against the id that indexed it (Q6). A
  malicious or corrupt pack cannot inject content — worst case it fails verification
  and the client refetches loose. This is what makes publishing packs safe on hosts
  we do not control.
- **No new crypto and no new leak.** A pack is concatenated *already-encrypted*
  objects — no new key, no re-encryption. It reveals object count and sizes, which a
  directory-listing static host already reveals. Worth one line in the docs, not a
  design change.

**Recommended sequencing:** ship the transport first (it works today, §1), publish
`manifest.json` next (cheap, unblocks listing-dependent commands), and only then
packs — with the measurement above as the acceptance bar. Note that packs are a
*publish-format* question, so they belong in the same round as your `openapi.json`:
both are "what the publish step emits".

## 5. What we would like from you

1. **The reference vault's read key** (or a throwaway published vault) so we can close
   acceptance criterion **#1** against the real Pages deployment — we have #2 and #3.
   Today's GitHub incident makes that a nicely-timed test of exactly the failure mode
   this feature exists for.
2. **Confirm the static layout convention** you are publishing (`api/vault/read/...`
   vs objects at root). We sniff both, so either works — we would just rather sniff
   one and log it than support two forever.
3. **Your view on C1** — whether your projection publishes large blobs at their normal
   object path (we assume yes, which is what makes presigned-reads collapse to GETs).

---

*Spike: `scripts/spike__static_vault_transport.py` (runnable, not shipped, not wired).
Measurements reproducible from the same file. Real-vault verification used the
`4bshby5n` backup supplied by the maintainer; its read key is not recorded here.*
