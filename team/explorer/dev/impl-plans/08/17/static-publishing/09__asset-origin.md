# 09 — A first-party asset origin (`static.sgit.ai`)

**Added:** 2026-08-19, from the maintainer's proposal — *"What if we publish that swagger js
into one of our `*.sgit.ai` or `*.sgraph.ai`… we could even create a `static.sgit.ai`
website (GitHub Pages) that we could use to publish all sorts of useful static resources
(logos, css) and to pin specific js dependencies."*

**Position: yes to the asset site, no to GitHub Pages, and no to it being on the reader's
critical path.** The right use is as the **publish-time source for `--api-docs=bundled`**,
which is strictly better than the jsdelivr fetch specified in `08` §3 — and strictly better
than being the runtime origin.

---

## 1. Three measurements that decide the hosting question

Probed 2026-08-19.

| Host | What it is | `cache-control` |
|---|---|---|
| `sgit.ai` | **GitHub Pages** (`server: GitHub.com`), ACAO `*` | **`max-age=600`** |
| `cdn.jsdelivr.net` | multi-CDN, purpose-built | `max-age=31536000, s-maxage=31536000, immutable` |
| **`static.sgraph.ai`** | **already live** — S3 `eu-west-2` behind **CloudFront** (`/` 403, `/index.html` 200) | per-object, configurable |

**GitHub Pages cannot serve immutable assets.** It stamps `max-age=600` on everything and
does not let you change it. A 1.53 MB bundle on Pages is re-fetched by every reader **every
ten minutes** instead of once a year — roughly two orders of magnitude more origin traffic
than the same file on jsdelivr, against Pages' documented **100 GB/month soft limit**. At
1.6 MB per docs-page load that cap is ~65,000 loads/month even with *perfect* caching, and
Pages' caching is the opposite of perfect.

**The host you want already exists.** `static.sgraph.ai` is S3 + CloudFront, where
`cache-control: public, max-age=31536000, immutable` is one object property. The Explorer
DevOps role already owns "sgit.ai deployment (S3/CloudFront)". So the convention is
deployed — it just should not be Pages.

**A second reason not to use Pages:** it would couple a vault published to S3 to GitHub's
availability. That is precisely the failure this whole feature exists to escape, and the
week that prompted the static-clone work was a GitHub outage.

## 2. The argument that actually decides it: we would become the thing we don't want to be

Today, a vault published to somebody else's host makes **zero requests to SGit-AI
infrastructure**. Nothing about a reader reaches us, because there is no code path by which
it could. That is structural, not a policy.

Put our JS on the reader's critical path and `static.sgit.ai` receives a request from **every
reader of every published vault**: IP, timing, volume, user-agent, and — without
`referrerpolicy="no-referrer"` — *which vault*.

| | jsdelivr learns | `static.sgit.ai` learns |
|---|---|---|
| what | "somebody loaded swagger-ui" | "somebody loaded swagger-ui" |
| correlation | none — no other signal about this person | **joins our logs, our domains, our accounts, our hub** |
| meaning | noise | a record tying readers of encrypted vaults to us |

The counter-intuitive conclusion is the right one: for an origin that may hold a reader's
key, **prefer the third party who cannot correlate over the first party who can.** A
zero-knowledge product does not get to say "we can't see your data" while operating the
beacon that every reader pings.

There is also a targeting asymmetry. A jsdelivr compromise is a broad-spectrum event; a
`static.sgit.ai` compromise is a precision weapon aimed at exactly the population holding
vault keys. SRI closes both equally — but it is worth being honest that we would be creating
the more attractive target, not a safer one.

### And it would be a permanent public commitment

Once a pinned URL is baked into published folders sitting on hosts **we do not control**,
that URL can never change. Delete it, rename it, tidy the repo, or let the bucket lapse, and
docs pages break forever on machines we cannot reach — no rollback, no patch, no notice. It
would have to be **append-only, never-rewritten, never-deleted, indefinitely**. That is a
real operational promise, and it is exactly the kind that gets broken in year two.

## 3. So use it where it is strong: publish-time, not read-time

`08` §3 has `--api-docs=bundled` fetching the pinned assets once and verifying them against
the SRI hashes. **Make `static.sgit.ai` that source.** Every concern above disappears,
because the fetch happens on the *publisher's* machine, once per version:

```
sgit publish --api-docs=bundled
  └─ cache miss for swagger-ui-dist@5.17.14?
       ├─ GET https://static.sgit.ai/vendor/swagger-ui/5.17.14/…   (primary)
       ├─ GET https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/… (fallback)
       └─ verify sha384 against the pin  ──▶  cache  ──▶  copy into .sg_vault/publish/api/docs/
```

| | Reader | Publisher |
|---|---|---|
| external origins contacted | **none** | one, at publish time |
| what we learn about readers | **nothing** | — |
| what we learn about publishers | — | that a developer ran a publish, once per version per machine |

It is also strictly *better* than the jsdelivr-only fetch: it works in corporate networks
that block public CDNs, it survives an npm/jsdelivr incident, and the **hash decides**, so a
mirror can never substitute bytes — a compromised mirror fails closed rather than shipping
code. That is the property that makes a first-party mirror safe here and unsafe in §2: at
publish time the pin is checked by us; at read time it would be checked by a page whose
integrity attribute we also authored.

## 4. The line to draw, once, so it does not erode

Split by **whether the consuming page may hold vault key material**:

| Consumer | First-party assets? |
|---|---|
| `sgit.ai`, `hub.sgit.ai`, docs, READMEs, release pages, install scripts, `versions.json`, brand CSS, logos, OG images | **Yes — do it.** No concern at all; this is the useful half of the idea |
| A **published vault folder** — loader, cover, docs page, anything on an origin that may hold a read key | **No.** Bundle it, or CDN+SRI |

**The loader is the case that will be argued.** It is byte-identical across every non-overriding vault
(invariant 4) and self-contained; a logo referenced from `static.sgit.ai` would be a beacon fired on every
single vault view, forever, from every host. Inline it as a `data:` URI or take it from the
vault. "It's just a logo" is precisely how a first-party origin ends up on every reader's
critical path.

## 5. If it is built anyway, these are non-negotiable

1. **S3 + CloudFront, not Pages** — `max-age=600` makes Pages unfit for versioned assets.
2. **Immutable versioned paths**: `/vendor/swagger-ui/5.17.14/swagger-ui-bundle.js`. Never
   `/latest/`, never overwritten. With SRI in the wild, one overwrite breaks every published
   page that references it, permanently.
3. **`cache-control: public, max-age=31536000, immutable`** on everything under `/vendor/`.
4. **Never a `Domain=.sgit.ai` cookie** anywhere in the estate, or the static host starts
   receiving them.
5. **Publish the SRI hash next to every asset** (`…/5.17.14/SHA384SUMS`), so a consumer can
   verify our mirror against upstream rather than trusting it.
6. **ACAO `*`** so `crossorigin="anonymous"` (required for SRI) works — Pages already does
   this by default, CloudFront needs it configured.
7. Treat it as **append-only for anything referenced from a published artefact**.

## 6. What changes in this pack

- `08` §3: `--api-docs=bundled` fetches from `static.sgit.ai` **first**, jsdelivr as
  fallback, verified against the same pin. No change to `=cdn` (still jsdelivr, still not us).
- `06`: decision 10 — build the asset origin, on S3/CloudFront, scoped to first-party
  properties plus publish-time vendoring.
- No change to any invariant. I2 ("the server never receives the key") is unaffected either
  way; the concern in §2 is disclosure of *readership*, which no current invariant covers —
  and arguably should, if a first-party origin ever gets closer than this.
