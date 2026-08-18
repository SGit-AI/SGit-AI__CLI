# Pack — Static Publishing, `sgit vault serve`, and the Publishing Matrix

**Version:** v0 · **Date:** 2026-08-17 · **Owner:** sgit CLI team
**Status:** BUILD SPEC — ready to implement. Six decisions (§`06`) want the maintainer's
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
| [`04__invariants-and-tests.md`](04__invariants-and-tests.md) | The 5 invariants as automated assertions, the 14 test cells → files | QA, or building it |
| [`05__implementation-phases.md`](05__implementation-phases.md) | P1–P7 with file lists, acceptance criteria and risk | planning or building |
| [`06__decisions-and-evidence.md`](06__decisions-and-evidence.md) | Open decisions for the maintainer + the measured evidence base | the maintainer |

## Reading order by audience

- **Developer agent:** `00` → `01` → `05`, then `02`/`04` for the phase you are on.
- **Maintainer:** `06` first (decisions), then this README, then `02` (what users will see).
- **QA:** `04`, then `03` for the flows the cells exercise.
- **SG/API or Web team:** `01` (layout + manifest contract) and `06` (what we measured
  about your platforms).

## Two things already settled by measurement

Both reverse or sharpen an assumption in the source briefs; details and reproduction in
[`06__decisions-and-evidence.md`](06__decisions-and-evidence.md).

1. **GitHub Pages *does* permit cross-origin reads** (`access-control-allow-origin: *` by
   default). Key-on-another-origin is supported, not unavailable.
2. **Custody without access requires a manifest.** Every filename in a vault derives from
   the read key, so a keyless client cannot name a single file. `manifest.json` is
   therefore required, not an optimisation.

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
