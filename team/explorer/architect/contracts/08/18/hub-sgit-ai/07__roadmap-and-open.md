# 07 — Roadmap, Absences & Open Questions

## 1. Build order

The forge brief's sequence, adjusted for what the audit found and for the fractal.

| # | Step | Why here | Depends on |
|---|---|---|---|
| 0 | **The two audits** — web-side capability audit; decide the sub-vault question | architecture written before these is wrong in one of two expensive directions | — |
| 1 | **Read-only forge view over one public vault** — browse, diff, history | the demonstration; achievable now; no accounts, no server logic | web audit |
| 2 | **The same view over a private vault**, key supplied by the visitor | **this is what makes it a forge rather than a public gallery** — prioritise it over tier work | 1 + the key-handling rules |
| 3 | **The ciphertext panel** (`06` §1) | the argument; design it in, don't bolt it on | 1 |
| 4 | **Hub index = a vault with a catalogue** | makes the hub itself a vault; unlocks the fractal | `sgit publish` (P2/P4) |
| 5 | **Fractal navigation** — `kind: hub` entries, visited set, depth bound | the community/adoption mechanism | 4 |
| 6 | **Structure-key view** | shipped primitive, no consumer; a tier no forge can express | web audit |
| 7 | **Issues as vault files** | existing mail/messaging work covers most of it | 2 |
| 8 | **Change proposals** — serialised diff, reviewed in the browser | needs no credential on the target | 7 |
| 9 | **Discovery across public vaults** | the only part needing a reading index | 4 |
| 10 | **CI by scoped vault** | hardest and most interesting; gated on the sub-vault decision | 0 |

Step 2 is the one worth prioritising over tier work. Step 5 is the one that turns a product
into an ecosystem.

## 2. The four absences — state them, do not defer them

The pack is more credible for naming these, exactly as the limitations page makes the rest
of the site credible.

| Absent | Why |
|---|---|
| **Search across vaults you hold no key to** | requires a reading index; possible only for published-key vaults |
| **Continuous integration** | a runner must read to build; the model-consistent answer is a scoped vault key, and it needs an assembler |
| **Server-enforced granular permissions** | possession of a key is access; there is nothing for a server to withhold |
| **Content-triggered notifications / webhooks** | the server cannot see what changed |

And the classification rule the specification asks for, applied per feature:

| Category | Examples |
|---|---|
| **Surfacing** what sgit already does | browse, diff, history, branch, merge, sparse fetch, per-path index |
| **Adding** something computed client-side | **blame** (confirmed absent from the CLI), within-vault search, the ciphertext panel, structure-only views |
| **Absent**, with a reason | the four above |

## 3. Open questions

### Blocking

| # | Question | Owner | Note |
|---|---|---|---|
| 1 | **Sub-vaults: option A, B or C?** (`04` §4) | Architect + CLI | the permissions model and the CI answer both rest on it; **A recommended** |
| 2 | **Web capability audit** | Web team | the specification's first deliverable; still the gate |
| 3 | **Storage economics** | Strategy | ciphertext neither compresses nor dedups; unmodelled since 14 Aug and it decides pricing |

### Important

| # | Question | Note |
|---|---|---|
| 4 | Catalogue schema, incl. `kind: vault \| hub` and provenance fields | fix it early — it is the fractal's only contract |
| 5 | Discoverability | the site is not indexed for its own language; a hub inherits that problem multiplied |
| 6 | Abuse handling on unreadable content | the unit of action is the vault; needs a stated policy **before** launch |
| 7 | Operational commitments: no password reset by design, uptime, escrow | named 14 Aug, none resolved |
| 8 | Does the hub run its own mirrors, or is mirroring a third-party product? | custody-without-access makes the latter possible and differentiating |

### Answered since the briefing pack was written

| Question | Answer |
|---|---|
| *"Whether content-addressed identifiers survive a rekey"* — listed as open, and as a protocol decision | **Settled by measurement: they do not.** Ids are `sha256(ciphertext)` with a random IV for blobs. Two vaults with the same document share **zero** ids; a rekey turns over **100%**. A private fork of a public template leaks nothing, and **no protocol change is needed**. Corollary: template-diffing by identifier is impossible |
| *"How does a visitor supply a key safely?"* | fragment → stored → service → paste, with classify-by-declaration and refuse-vault-key. Rules in `03` §4.2; the CLI ships the classifier |
| *"Is sparse fetching the default?"* | it should be, and the capability exists (`Vault__Sync__Sparse`) |
| *"Does a flat object directory breach the 3,000-entry guidance?"* | yes; sharding designed (`contracts/08/14/`), awaiting SG/API + Web answers |
| *"Per-path indexes"* (v0.33.56) | **shipped** as the cache layer — 1-request reads for declared paths |

## 4. What each team owes

| Team | Owes |
|---|---|
| **Web** | the capability audit (§3 #2); the loader rules from `03` §4.2; the ciphertext panel |
| **CLI (us)** | `sgit publish` / `serve` / `mirror` (dev pack, 08/17); the sub-vault decision and, if A, the link schema + resolver; a consumer for the structure key |
| **SG/API** | answers on sharding; confirmation that nothing server-side parses `bare/data/` structure |
| **Strategy** | storage economics; the operational commitments; the commercialisation model in `05` |

## 5. Three things not to get wrong

Carried forward from the leading brief because they remain true and remain easy to get wrong:

1. **Do not call reusable components "plugins."** That word already means a capability grant
   in this product, and the vault runtime ships a deny-by-default permission model on that
   basis. Use *component* or *starter*.
2. **Do not publish write keys.** Read keys for public vaults may be catalogued; a central
   list of vault keys would be a single artefact whose compromise is unbounded.
3. **Do not assume a published vault can be corrected.** A vault whose write key is lost is
   frozen — readable forever, never updatable, never revocable. **Escrow the write key
   before publishing**, which is a precondition rather than good practice.

## 6. The trust model, in one line

> **Publishing a vault is publishing a repository. Once the key is out, clones exist and
> cannot be recalled. The difference is that the host still cannot read it.**
