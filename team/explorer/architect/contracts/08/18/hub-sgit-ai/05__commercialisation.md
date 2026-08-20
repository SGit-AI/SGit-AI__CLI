# 05 — Commercialisation: What You Can Charge For When You Cannot Read

Not covered by the briefing pack; raised by the maintainer on 18 Aug. The question is
sharper than it looks, because the property being sold **removes the incumbent's business
model** rather than competing with it.

---

## 1. The inversion: privacy is free here, so it cannot be the product

GitHub's original pricing was **private repositories**. That works because privacy costs the
host something: the server *can* read, so *not* reading is a policy it maintains, enforces
and charges for.

On a blind host, **privacy is the default and costs nothing extra**. The bytes for a public
and a private vault are identical — proven, it is the "one deployment, two link modes"
property. There is no "private tier" to sell because there is no public tier to downgrade
from.

```
   FORGE                              VAULT FORGE
   free:  public repos                free:  everything is private already
   paid:  private repos               paid:  ???  ← privacy is not a feature you can withhold
   paid:  seats (server enforces)     paid:  ???  ← the server enforces nothing
```

That is not a problem to solve — it is a **positioning gift**, because "we cannot sell you
privacy because you already have it" is a strong sentence. But it means the revenue has to
come from the four things a blind host genuinely provides.

## 2. The four things you can legitimately charge for

### 2.1 Durability and availability — the objects have to live somewhere

The most honest line item and the least glamorous. Storage, bandwidth, egress, retention,
replicas, and an uptime promise. Notes specific to this system:

- **Encrypted objects neither compress nor deduplicate**, so the usual hosting economics do
  not transfer: cost grows linearly with content, and there is no dedup win from many users
  storing the same dependency. Model this before pricing anything. *(Flagged unmodelled
  since 14 Aug; still unmodelled.)*
- **Replication is not backup.** A bad change propagates to every replica; version history
  supplies the time dimension. So "we keep N copies" and "you can go back" are **two
  different products**, and the second is the valuable one.
- Custody-without-access makes **third-party mirroring** sellable: a mirror operator needs no
  trust and no key, so "an independent party holds a verifiable copy of your estate and
  cannot read it" is a service that is impossible on a conventional host.

### 2.2 Namespace and identity — the one identity question there is

Reading needs no identity. **The hub's only identity question is *who may publish to this
namespace*** — which is exactly what a package registry answers, and exactly what
registries charge for.

- `acme/…` on a hub, verified ownership, protected names.
- Publishing rights, org membership, audit of who published what and when.
- This is a **write-path** product and it does not compromise the blindness claim at all.

### 2.3 Discovery, curation and provenance — the only reading feature that exists

Search across vaults you hold no key to is impossible *except* for vaults whose owner
published the key. So indexing public vaults is a legitimate, owner-consented service — and
scarce, because nobody else can do it either.

Sellable: placement and prominence, verified-publisher badges, curated collections, topic
sections, quality/provenance signals ("who listed this, when, what did they check").
**Not** sellable: anything that requires reading private content.

### 2.4 Compute the client cannot do — CI, at scope

The genuine hole is the genuine opportunity. A build runner must read, so a hosted build is
a **key-holding service** — which is only defensible when scoped (a vault containing only
what the build needs). That is hard, it is valuable, and it is charged for by the minute
everywhere else. It is also the one place where the honest answer is "you are trusting us
with this scoped key", and that must be said out loud.

## 3. The fractal is the distribution model, and it changes the shape of the business

Because a hub costs nothing to run, the market is not "who hosts your repos" but "whose hub
do you appear in". That suggests:

| Layer | Free | Paid |
|---|---|---|
| **The format** | always — a folder anyone can copy | never |
| **Self-run hub** | always — `sgit publish` to a bucket | support, distributions, hardening |
| **Hosted hub** | small estates, public vaults | storage, durability, SLA, namespace |
| **The index** | listing yourself | prominence, verification, curation |
| **Compute** | none | scoped CI |
| **Enterprise** | — | private hub distribution, audit, escrow, mirroring, key-management guidance |

**Escrow deserves a line of its own.** A vault whose write key is lost is **frozen** —
readable forever, never updatable, never revocable — and the project has already hit this.
"Escrow the write key before publishing" is a *precondition*, not good practice. A key-escrow
service is therefore a real enterprise product, and it is one where the operator's inability
to read is the selling point: escrow the **write** key under the customer's own control, and
the hub still reads nothing.

## 4. What must never be monetised

Each of these breaks the claim that everything else rests on:

- **Reading customer content** — for search, analytics, ML training, "insights", or ads.
  The catastrophic-failure principle is a *design test*: any feature that fails it is out.
- **Selling the shape as data.** The estate's shape *is* disclosed to the operator (how
  many vaults, how big, how often they change) — that is the stated exception to the
  principle. Disclosing it is unavoidable; **selling** it is a choice, and it would poison
  the pitch.
- **Charging for privacy.** It is the default; pricing it implies it is withheld.
- **Anything that makes the operator a required intermediary.** The moment a hub is
  necessary rather than convenient, the fractal stops being real and so does the pitch.

## 5. The honest risks

| Risk | Note |
|---|---|
| Storage economics are unmodelled | ciphertext does not compress or dedup; the margin structure is not a code host's |
| No lock-in by design | the artefact is a folder anyone can copy — retention has to be earned, every year |
| Operational commitments arrive with the first customer | **no password reset by design**, uptime as a promise, abuse handling as a function with an owner. All named 14 Aug, none resolved |
| Abuse handling on unreadable content | the unit of action is the vault, not the file; a host that cannot read cannot triage — this needs a stated policy before launch, not after |
| CI is the one trusted service | it must hold a key; scope it and say so plainly |
| Discovery depends on discoverability | the site is not indexed for its own language; a hub whose purpose is that people find vaults inherits that problem multiplied |

## 6. The one-line positioning

> **We cannot sell you privacy, because you already have it. We sell durability, a
> namespace, discovery, and the compute you cannot run yourself — and we still cannot read
> a single byte of your work.**
