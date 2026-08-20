# DEV BRIEF — hub.sgit.ai

**For:** the agent building the hub (or the CLI-side pieces it needs) · **Date:** 2026-08-18

Launch with:

> Read your role definition and the repo `CLAUDE.md`. Then read
> `team/explorer/architect/contracts/08/18/hub-sgit-ai/00__DEV-BRIEF.md` and execute
> **Step N** from it.

---

## 1. Read these first, in this order

1. This file.
2. [`01__the-model-and-the-fractal.md`](01__the-model-and-the-fractal.md) — the model is
   **settled**; do not relitigate it. The fractal section is new (18 Aug).
3. [`02__capability-audit.md`](02__capability-audit.md) — **what already exists.** The CLI
   half is done; the web half is Step 0.
4. Your step's section in [`07__roadmap-and-open.md`](07__roadmap-and-open.md).

Reference as needed: `03` (architecture/flows), `04` (permissions), `05`
(commercialisation), `06` (mockups).

Related, already built: `team/explorer/dev/impl-plans/08/17/static-publishing/` — the
publish/serve/mirror commands the hub is assembled from.

## 2. Step 0 comes before architecture — and it is not optional

The specification (v0.33.58 Part B) is explicit, and it is right:

> *"The pack cannot be written honestly until somebody establishes what the existing vault
> web codebase already does… a design written without that inventory will either duplicate
> what exists or assume capabilities that do not."*

**Two things must land before hub architecture is written:**

**0a. The web capability audit.** Template in `02` §4. For each capability: present /
partial / absent, where it lives, reachable from a page. **Report gaps as plainly as
presences** — a partial capability is more dangerous to a plan than an absent one, because
it will be assumed complete. Two rows were added to the original list: *structure-key open*
and *sub-vault traversal*.

**0b. The sub-vault decision.** See §4 below. It is the one that changes the shape of
everything after it.

## 3. The rules that override convenience

1. **The server reads nothing, ever.** Any feature that requires the hub to read content is
   out — not deferred, out. The catastrophic-failure principle is a *design test*: if a
   total compromise of the hub would disclose content that was not already public, the
   feature fails.
2. **Features follow the key, not the tier.** Anything a user holds a key to gets the full
   experience, public or private. Only *discovery across vaults you hold no key to* needs a
   reading index.
3. **Classify keys by declaration, never by shape**, and **refuse a vault key** in any read
   surface. The CLI ships the classifier (`Vault__Crypto.classify_key` → `Enum__Key_Kind`);
   port it, do not reinvent it.
4. **Never imply a capability that does not exist.** No revoke button (revocation is not
   retroactive). No search box that silently searches only what you hold.
5. **Sparse by default.** The honest performance claim — *scales with what you look at, not
   with the size of the vault* — is only true if the interface behaves that way.
6. **A hub is a vault.** If you find yourself adding a server-side feature to make hubs
   talk to each other, stop: the fractal is client-side graph navigation, and needs no
   federation protocol.

## 4. The decision to make before building permissions

Every brief describes granularity as *"sub-vaults with their own keys, link files"*.
**That primitive does not exist in the CLI** (audit §2). Three options, in `04` §4:

- **A — separate vaults + a link convention** (recommended): small, no format change, and
  it is the same mechanism the fractal already needs.
- **B — nested sub-vaults with derived keys**: a real protocol project (wire format,
  cross-runtime, migration). Do not let it gate the hub.
- **C — per-path content keys**: not recommended; breaks CAS dedup and complicates rekey.

Raise this; do not resolve it in code.

## 5. Steps

| Step | Build | Gate | Notes |
|---|---|---|---|
| **0** | web capability audit + sub-vault decision | — | **blocks everything**; publish the audit, it is useful on its own |
| **1** | read-only forge view over one **public** vault | 0a | browse, diff, history. The demonstration |
| **2** | the same view over a **private** vault, visitor supplies the key | 1 | **the step that makes it a forge, not a gallery** — prioritise over tier work |
| **3** | the **ciphertext panel** (`06` §1) | 1 | live request list, not illustrative. Design it in |
| **4** | hub index = a vault with a catalogue | `sgit publish` | fixes the catalogue schema — get `kind: vault \| hub` in from the start |
| **5** | fractal navigation | 4 | **carry a visited set and a depth bound** — the graph has cycles |
| **6** | structure-key view (`06` §3) | 0a | shipped primitive, no consumer; a tier no forge can express |
| **7+** | issues → change proposals → discovery → scoped CI | | see `07` §1 |

**CLI-side work** (ours, parallel to the above): `sgit publish` / `serve` / `mirror` per the
08/17 pack; the link schema + resolver if option A is chosen; a consumer for the structure
key.

## 6. Definition of done, per step

- [ ] Nothing added that requires the hub to read content (rule 1) — say so explicitly in
      the PR if you touched anything near the boundary
- [ ] Every capability you used is recorded in the audit as present, or you added it and
      said so (**surfacing vs adding vs absent** — `07` §2)
- [ ] Sparse fetch used for anything that browses
- [ ] Key handling follows rule 3, including the vault-key refusal
- [ ] For UI: the tier a reader is in is visible (public / trusted / structure-only)
- [ ] For fractal work: cycle-safe, depth-bounded, and stale-head age surfaced

## 7. What is NOT yours to decide

- The **sub-vault option** (§4) — recommend, do not implement B or C unilaterally.
- **Any wire or key format change** — cross-runtime contracts shared with SG/API, SG/Vault
  web and the CLI.
- **Whether to publish a write key** — never; there is no case.
- **Commercial model** (`05`) — that is Strategy's; it is in this pack for context.
- **Anything that makes the hub a required intermediary.** The moment a hub is necessary
  rather than convenient, the fractal stops being real.

## 8. When you get stuck

- **A feature seems to need server-side reading** → it is one of the four stated absences,
  or it needs restating as a client-side capability. Check `07` §2 before building.
- **You need finer permissions than "a vault"** → that is §4, unresolved. Model it with
  separate vaults for now and flag it.
- **Something looks like a protocol change** → stop and write it up. Cheaper now than after
  release, and the last three of these turned out to be measurable in an afternoon.
- **A brief contradicts the code** → the code wins, and tell us: two of the briefing pack's
  open questions were already settled by measurement (`07` §3).
