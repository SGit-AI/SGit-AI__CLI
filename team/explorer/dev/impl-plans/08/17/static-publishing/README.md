# Pack — Static Publishing, `sgit vault serve`, and the Publishing Matrix

**Version:** v0 · **Date:** 2026-08-17 · **Owner:** sgit CLI team
**Status:** BUILD SPEC — ready to implement. Eleven decisions (§`06`) want the maintainer's
sign-off, but Phases 1 and 3 are unblocked and can start now.

Implements the 08/16 publishing-matrix dev brief, the publish-protocol brief, and the
loader-page brief, for the SGit-AI CLI.

---

## The feature in three sentences

A vault publishes to a **folder**: encrypted objects plus a small, declared plaintext
surface (loader, cover, manifest, and — only when the vault is deliberately public — the
read key). That folder is readable by a **browser** through the loader and by **`sgit
clone`** over ordinary GETs, from any HTTP host or a local/networked folder, with no
server and no auth. `sgit vault serve` exists because browsers give local files an opaque
origin, so the one case everybody tries first — double-clicking `index.html` — cannot work
without it.

## Files in this pack

| File | What it is | Read it if you are… |
|---|---|---|
| **[`00__DEV-BRIEF.md`](00__DEV-BRIEF.md)** | **The executable brief for a developer agent** — grounding reads, non-negotiable rules, per-phase tasks, definition of done | building it |
| [`01__architecture.md`](01__architecture.md) | The transport seam, publish-as-projection, the published layout, `manifest.json`, the plaintext-surface rule | building or reviewing it |
| [`02__commands-and-ux.md`](02__commands-and-ux.md) | Command surface and every CLI / loader mockup | building it, or writing docs |
| [`03__flows.md`](03__flows.md) | Sequence diagrams: publish → serve → read, static clone, fork | reviewing the design |
| [`04__invariants-and-tests.md`](04__invariants-and-tests.md) | The 6 invariants as automated assertions, the 14 test cells → files | QA, or building it |
| [`05__implementation-phases.md`](05__implementation-phases.md) | P1–P7 with file lists, acceptance criteria and risk | planning or building |
| [`06__decisions-and-evidence.md`](06__decisions-and-evidence.md) | Open decisions for the maintainer + the measured evidence base | the maintainer |
| [`07__publish-target.md`](07__publish-target.md) | **The publish output** — one fixed folder, target-agnostic, root-file overrides, what the deployer owns | building P2 |
| [`08__api-docs.md`](08__api-docs.md) | Optional `api/openapi.json` + Swagger UI in the published folder; CDN vs bundled | building P4b |
| [`09__asset-origin.md`](09__asset-origin.md) | `static.sgit.ai` — why first-party assets are fine at publish time and wrong at read time | DevOps, or the maintainer |
| [`10__tabletop__github-pages-one-repo.md`](10__tabletop__github-pages-one-repo.md) | **Executed end-to-end tabletop**: one repo carrying read key + decrypted files + vault, deployed to Pages, cloned back — real CLI throughout | everyone, before building P2 |
| [`CHANGELOG.md`](CHANGELOG.md) | **Change control** — every revision of this pack, what changed, why, and the commit | anyone returning to the pack |

## Reading order by audience

- **Developer agent:** `00` → `01` → `05`, then `02`/`04` for the phase you are on.
- **Maintainer:** `06` first (decisions), then this README, then `02` (what users will see).
- **QA:** `04`, then `03` for the flows the cells exercise.
- **SG/API or Web team:** `01` (layout + manifest contract) and `06` (what we measured
  about your platforms).

## Six things already settled by measurement

Each reverses or sharpens an assumption — including two of our own; details and reproduction
in [`06__decisions-and-evidence.md`](06__decisions-and-evidence.md).

1. **GitHub Pages *does* permit cross-origin reads** (`access-control-allow-origin: *` by
   default). Key-on-another-origin is supported, not unavailable.
2. **Custody without access requires a manifest.** Every filename in a vault derives from
   the read key, so a keyless client cannot name a single file. `manifest.json` is
   therefore required, not an optimisation.
3. **`sgit publish` has no target argument.** Published files anywhere but `.sg_vault/` are
   ordinary content to `sgit push`, so publish → push → publish would double the store on
   every cycle, silently. One fixed output folder removes the question rather than policing
   it ([`07`](07__publish-target.md)).
4. **Swagger UI is 1.53 MB — ~2.7× the vault it documents.** With an exact version pin and
   SRI, CDN delivery is the better default and vendoring is the opt-in
   ([`08`](08__api-docs.md)); this reverses the pack's first recommendation.
5. **A repo that commits `.sg_vault/bare` is already a statically clonable vault** — the
   19 Aug tabletop cloned one with shipped code and no publish step. Publish adds the
   loader, custody manifest, and key discovery — not clonability
   ([`10`](10__tabletop__github-pages-one-repo.md)).
6. **Publish needs only the read key** — the commit parent-walk and ref decrypt ran from
   the committed `sgit_public_read_*` filename alone, which is what lets a public vault's
   Pages workflow republish with zero secrets ([`10`](10__tabletop__github-pages-one-repo.md) step 9).

## Status of the parts

| Part | State |
|---|---|
| Static read transport | **proven** — `scripts/spike__static_vault_transport.py` clones from GitHub Pages, a dumb HTTP server, and a folder |
| Key formats (`sgit_public_read_` etc.) | **shipped** — commit `67c2ab6` |
| Rekey (= fork) | **exists** — `sgit vault rekey` / `move` |
| `sgit publish` | to build (P2, P4) |
| `sgit vault serve` | to build (P3) |
| `sgit vault mirror` | to build (P5) |
| Bundles | to build, deferrable (P6) |
