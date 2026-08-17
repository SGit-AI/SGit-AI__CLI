# CLI-Team Response — "One Deployment, Two Link Modes" (v0.33.59 loader-page brief)

**From:** sgit CLI team · **Date:** 2026-08-17
**Position:** the core architecture is right and mostly lands on Web, not us. Three
things land squarely on the CLI, and **one of them is a direct collision with a
security feature we shipped three days ago** that will fire the first time anyone
publishes a public vault from a git-hosted static site.

---

## 1. Agreed, and it composes with what already works

"The published ciphertext is identical for a public and a private vault" is exactly
right, and our static-transport spike is the CLI-side proof: the same bytes clone
from a folder, from a dumb GET server, and from a CDN, with the read key supplied
out of band. Nothing in the publish artefact knows or cares. The link-time decision
is real.

The fragment reasoning is correct and I have nothing to add to it — it is Web's
domain and the brief handles it properly.

## 2. **The collision: `sgit_rk1_` is a leak alarm, and this design publishes it**

On 14 August we shipped self-identifying key prefixes *specifically so that a leaked
read key is detectable*: `sgit_rk1_<64-hex>` exists to be caught by gitleaks, GitHub
push protection and pre-commit hooks. The regex is deliberately unambiguous:
`\bsgit_rk1_[0-9a-f]{64}\b`.

This brief proposes putting exactly that string into a loader page — and GitHub Pages
deployments *are git repositories*. So publishing a public vault will:

1. trip secret scanning / push protection on the publishing repo, and
2. worse, **train people to ignore read-key alerts**, because most of them will be
   deliberate. An alarm that is usually a false positive stops being an alarm — which
   destroys the detection value we just built.

**Proposed resolution: a third prefix that declares intent, not type.**

| Prefix | Same bytes as | Meaning | Scanner rule |
|---|---|---|---|
| `sgit_rk1_` | — | read key, **private** | **alert** — a leak |
| `sgit_pk1_` | identical read key | read key, **deliberately published** | **ignore** |
| `sgit_vk1_` | — | vault key (write capability) | **alert, always** |

The key material is byte-identical; only the declaration differs, exactly as
`sgit_vk1_` was byte-identical to the legacy key. `sgit publish --public` emits
`sgit_pk1_`; a human or a scanner can then tell "this vault was meant to be open"
from "somebody pasted a key into a repo". Cheap to implement (one more accepted
prefix in `strip_key_prefix`, already the single normalisation point).

This also answers the brief's open question *"Does the loader advertise which mode it
is in?"* — **the key format itself advertises it**, with no extra UI and no way for
the page to be wrong about it.

## 3. The loader must refuse a vault key — and prefixes make that possible

The discovery order (fragment → stored → service → ask) ends in a paste field. That
field will, eventually, receive a **vault key**, because users do not reliably
distinguish their credentials. A vault key in a loader page hands **write capability**
to a web page whose whole security argument is that it only ever needed read
capability.

With prefixes this is a two-line check rather than a guess:

- `sgit_pk1_…` / `sgit_rk1_…` / bare 64-hex → read key, proceed
- `sgit_vk1_…` → **refuse**: *"That is your vault key, which can modify this vault.
  A reader only needs your read key — run `sgit vault derive-keys` to get it."*
- anything else → reject before touching crypto

Without prefixes the loader has to classify by shape (64-hex vs `something:something`),
which is exactly the guess-by-shape heuristic that already bit us once in the CLI
(and which we fixed on 15 August by making explicit prefixes beat the heuristic —
same rule, same reasoning, please mirror it).

## 4. Revocation on git-hosted static is worse than the brief states — measured

The brief says rotation needs the write key and a published key cannot be withdrawn.
Both true. The static case adds two facts we measured:

```
before rekey: vault_id = hgnxqbif   5 objects   obj-cas-imm-1a1f9c1b7536
after  rekey: vault_id = fv09jdl4   5 objects   obj-cas-imm-6e5d4d66f70f
  vault_id changed         : True
  ANY object id preserved? : False   <- zero overlap
```

1. **Rotation republishes everything at completely new paths.** Object ids are
   `sha256(ciphertext)[:12]`, so re-encryption changes every id and the vault id too.
   A rotated vault is not an updated deployment, it is a *new* one; the old tree must
   be deleted, not superseded.
2. **On a git-hosted static site, deletion does not delete.** GitHub Pages serves from
   a repo, and removing the old objects in a later commit leaves them in history,
   fetchable by anyone who can clone — which for a public Pages repo is everybody.
   So **a public-repo static vault cannot revoke read access at all**, even *with* the
   write key: rotation only stops new content from being readable, while every byte
   published under the old key stays recoverable from git history forever.

That is a stronger statement than "a frozen vault cannot reduce readership" and it
deserves to be in the pattern's limits section. The practical guidance: treat
publishing to a git-hosted static site as **irreversible disclosure of everything in
that publish**, and if that is not acceptable, publish to object storage (S3/CDN)
where delete means delete.

## 5. Two open questions we can answer now

**"Does the loader work offline once cached?"** — Split answer:

- **CLI: yes, proven.** Our spike clones a real vault from an unpacked folder with no
  network at all, using the read key alone.
- **Browser: no, not from `file://`.** A loader page opened directly from disk cannot
  `fetch()` its sibling objects — Chrome treats `file://` documents as opaque origins
  and blocks the reads. An offline browser deployment needs a local static server
  (`python -m http.server`) or a packaged context (extension / PWA cache). Worth
  stating so nobody builds toward the `file://` case and discovers this late.

**"How large is a self-contained loader?"** — Smaller than the tension table assumes,
because **the vault protocol needs no crypto library at all**. Every primitive is
native Web Crypto: AES-256-GCM, HKDF-SHA256, PBKDF2-SHA256, SHA-256, HMAC-SHA256, and
P-256 for signature checks. A self-contained loader therefore ships protocol logic
only — id derivation, tree walk, checkout — not crypto. That materially strengthens
the "self-contained first" recommendation: the supply-chain-free option is not paying
a large size penalty for its safety.

## 6. What the CLI should own (build-order steps 1–2)

The brief's step 2 — *three description settings as a publish-time option rather than
a hand-edited page* — is ours. Our position:

- `sgit publish` emits the loader, and **key visibility is an explicit flag**, never a
  default and never inferred: `--visibility bare|named|public`.
- `--visibility public` must **print what it is doing in plain words** ("this
  deployment publishes the read key: anyone with the URL can read all content, and
  this cannot be undone for content published now") and, on a git-hosted target, add
  the §4 irreversibility warning.
- The setting is **recorded in the vault**, so a republish cannot silently flip a
  private vault to public by inheriting a different default. This is the same class of
  bug as the cache layer's "silent rewrite in a fail-soft layer" — a visibility
  default that drifts is a disclosure.
- Default is **bare**, matching the brief's own safest-default reasoning.

We agree with "self-contained first, and the pinning discipline decided before the
first external script." Given §5's finding that no crypto library is needed, we would
go further: **the first external script should have to justify itself in writing**,
because the baseline it is competing against has no supply chain at all.

## 7. One framing note on "who sees the read key is a business decision"

Agreed, and the CLI's job is to make that decision **explicit, recorded, and
auditable** rather than emergent. Concretely that means: an explicit flag (never a
default), a stated consequence at publish time, the choice stored with the vault, and
a key format that carries the intent (`sgit_pk1_` vs `sgit_rk1_`) so the decision
remains legible to humans and machines long after the person who made it has moved on.

---

## Asks

1. **Adopt `sgit_pk1_`** (or tell us the collision in §2 is acceptable and you will
   allowlist per-repo — but we think that scales badly and erodes the alarm).
2. **Mirror the prefix-beats-heuristic rule** in the loader's key classification, and
   **refuse `sgit_vk1_`** outright (§3).
3. **Add §4 to the pattern's limits** — irreversible disclosure on git-hosted targets
   is a materially different risk from the API-hosted case.

*Evidence: rotation figures reproducible in-repo; static-folder clone proven by
`scripts/spike__static_vault_transport.py`; prefix behaviour pinned by
`tests/unit/crypto/test_Vault__Crypto__Key_Prefixes.py`.*
