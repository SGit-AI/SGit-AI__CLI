# Pack — hub.sgit.ai: The Fractal Forge

**Version:** v0 · **Date:** 2026-08-18 · **From:** sgit CLI team (Explorer / Architect)
**Responds to:** the 15-document hub briefing pack (v0.33.56–v0.33.59), and adds the three
dimensions the maintainer raised on 18 Aug: **community-run hubs**, **fractal
hub-of-hubs**, and **commercialisation**.

**Status:** design pack. Two findings below change the plan materially, and one of them
should be resolved before hub architecture is written.

---

## The hub in four sentences

A **forge whose application layer is the browser**: the client holds the key, the server
stores ciphertext and reads nothing. A hub is **itself a vault** — a cover, a catalogue,
and a loader — which means a hub can list other hubs, and the network is **fractal** by
composition rather than by new protocol. Everything on a hub is encrypted except the few
vaults an owner deliberately publishes, so the public surface is a **choice per vault**,
not a tier of the product. Anyone can run one, because "run a hub" means "publish a folder".

## Two findings that change the plan

Both are facts about the shipped CLI, established for this pack (details in
[`02__capability-audit.md`](02__capability-audit.md)).

1. **The permissions model rests on a primitive that does not exist.** Every brief builds
   granularity on "sub-vaults with their own keys, link files". **There is no sub-vault or
   link-file primitive in the CLI.** The scoped-sub-vault answer for CI, and the worked
   topologies the spec asks for, currently have nothing to stand on. This is the single
   most important thing to resolve before architecture.
2. **There is a third access tier already shipped, and nobody is using it.**
   `derive_structure_key` produces a key that decrypts **metadata but not content** —
   paths, tree shape, history, sizes — with one consumer (`sgit vault dump`). That is
   exactly "browse the shape without reading the files", which is a hub feature, a
   permissions tier, and a commercial tier, all already implemented and tested.

## Files

| File | What it is |
|---|---|
| **[`00__DEV-BRIEF.md`](00__DEV-BRIEF.md)** | **The executable brief.** First deliverable is the audits — not architecture |
| [`01__the-model-and-the-fractal.md`](01__the-model-and-the-fractal.md) | The forge model, and the fractal hub-of-hubs: a hub is a vault |
| [`02__capability-audit.md`](02__capability-audit.md) | CLI-side audit **done** (facts); the web-side audit template the spec asks for |
| [`03__architecture-and-flows.md`](03__architecture-and-flows.md) | Diagrams, the ciphertext boundary, the single-file data path, five user flows |
| [`04__permissions-topology.md`](04__permissions-topology.md) | Three tiers, worked topologies, the missing primitive, CI by scope |
| [`05__commercialisation.md`](05__commercialisation.md) | What you can charge for when you cannot read — and why the GitHub model inverts |
| [`06__mockups.md`](06__mockups.md) | Interface mockups, including **the one screen that matters** |
| [`07__roadmap-and-open.md`](07__roadmap-and-open.md) | Build order, the four absences, open questions, what we owe each team |

## Reading order

- **Whoever builds the hub:** `00` → `01` → `02` → `03`.
- **Maintainer / strategy:** `01` (the fractal) → `05` (commercialisation) → `07`.
- **CLI team:** `02` and `04` — the gaps are ours to close.
- **Web team:** `02`'s audit template is the first deliverable, and it is yours.

## What is already ours, and shipped

The hub is assembly, and more of the substrate exists than the briefing pack assumes:

| Foundation | State |
|---|---|
| Per-path indexes (v0.33.56 brief) | **shipped** as the cache layer — 1-request reads, D1–D10 |
| Read-key-only clone | **shipped** (v0.14.26+), verified against GitHub Pages |
| Static publishing / clone over GETs | **spiked and proven**; dev pack at `team/explorer/dev/impl-plans/08/17/static-publishing/` |
| Key declarations (`sgit_public_read_` etc.) | **shipped** — `67c2ab6` |
| Rekey = fork | **exists** (`sgit vault rekey`) — and forks are cryptographically unlinkable (measured) |
| Object-store sharding (assessment claim 7) | **designed**, awaiting SG/API + Web answers |
| Sub-vaults / link files | **absent** — see finding 1 |
