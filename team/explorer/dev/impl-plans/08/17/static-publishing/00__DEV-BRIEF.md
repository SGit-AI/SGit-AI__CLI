# DEV BRIEF — Static Publishing & `sgit vault serve`

**For:** a Developer agent (Explorer team) · **Owner:** sgit CLI team · **Date:** 2026-08-17

Launch with:

> Read your role definition at `team/explorer/dev/README.md` and the repo `CLAUDE.md`.
> Then read `team/explorer/dev/impl-plans/08/17/static-publishing/00__DEV-BRIEF.md`
> and execute **Phase N** from it.

Phases are independently shippable. Take one, finish it green, open a PR. Do not start a
later phase inside an earlier phase's PR.

---

## 1. Grounding reads, in this order

1. `CLAUDE.md` (repo root) — Type_Safe rules. **They are not optional**: zero raw
   primitives, classes not module functions, immutable defaults, round-trip invariant,
   naming conventions, no `__init__.py` under `tests/`.
2. `01__architecture.md` in this folder — the seam, the layout, the manifest contract.
3. `05__implementation-phases.md` — your phase's file list and acceptance criteria.
4. `scripts/spike__static_vault_transport.py` — **the design for P1 already exists as
   running code.** Promote it; do not redesign it.
5. `04__invariants-and-tests.md` — what your phase must not break.
6. `10__tabletop__github-pages-one-repo.md` — the whole flow, **executed**; if you are on
   P2, `scripts/tabletop__static_publishing/simulate_publish.py` is your first draft.
7. `11__tabletop__publishing-pipelines.md` + `templates/github-pages.yml` — the CI story,
   executed; if you are on P1 read finding F5, on P9 read F6 and
   `scripts/tabletop__static_publishing/attach_simulated.py` (your first draft).
8. `team/explorer/appsec/reviews/08/19/v0__appsec-review__static-publishing.md` — the security
   review. **SP-1 blocks P1, SP-8/SP-9 block P3, SP-3/SP-8 block P5** (they are in the phase
   acceptance lists); decision 16 (signed head) gates the private/CI tiers.
9. `12__accepted-risks.md` — what we are **deliberately not defending against** in v1 and
   why, plus decision 17's required implementation shape. Read it before P0, and before you
   "improve" any acceptance criterion that looks over-cautious — several encode a decision.

Skim only as needed: `02__commands-and-ux.md` (exact user-facing strings),
`03__flows.md`, `06__decisions-and-evidence.md`. If you are on P2 read `07__publish-target.md`
in full, and on P4b read `08__api-docs.md` in full — both carry acceptance criteria.

**Before trusting anything you remember from an earlier read, check `CHANGELOG.md`** —
this pack has revised load-bearing decisions several times. **Every PR that edits this
pack adds an entry there** (that rule is part of your definition of done).

## 2. The six rules that override convenience

These are the design's actual claims. A change that breaks one is wrong even if the tests
pass, so if you find yourself weakening one, stop and raise it instead.

1. **The ciphertext a reader receives is byte-identical to the store — because it IS the
   store.** `publish` never copies or transforms objects (r9); deployment places
   `.sg_vault/bare/**` by keyless copy (or co-locates it), and `serve` routes to it
   virtually. No destination-specific branch anywhere.
2. **The key never reaches a server.** Never in a path, never in a query. Fragment or
   file only.
3. **A keyless client can take custody** — mirror/copy a vault it cannot read. This is
   why `manifest.json` is mandatory.
4. **The loader is byte-identical everywhere.** `publish` always emits sgit's bundled
   template; a vault's own `index.html` is ciphertext at that moment and cannot change the
   output. The two only meet at deployment-time expansion (`07` §3).
5. **`publish` emits no vault content, ever.** Plaintext expansion is a deployment-time,
   key-holding act (`sgit vault expand`, P8 — deferred), and only *that* command enforces
   "expansion only where the key is published". The failure it guards is silent and
   permanent (git history).
6. **Publishing changes exactly one folder: `.sg_vault/publish/`.** There is no output
   directory argument, nothing else on disk is written, and deployment is somebody else's
   job. The output is target-agnostic — no `CNAME`, no `.nojekyll`, no host config in it.
   `07__publish-target.md`.

## 3. Non-negotiable implementation constraints

- **The plaintext surface is a fixed allow-list of names in code** — `index.html`,
  `cover.json`, `manifest.json`, and the public key file. Never a folder whose contents are
  emitted wholesale, and never a pattern: otherwise anyone who can write to the vault could
  widen the plaintext surface by adding a file. The allow-list decides *what may be
  plaintext*; the override rule (`07` §3) decides only *which source wins* for a name
  already on it. **`publish` emits no vault content whatsoever** — decrypted files reach a
  served root only through a deployment-time expansion by someone who holds the key. Every
  emitted plaintext file is recorded, with its `sha256`, in `manifest.json`.
- **Reads must stay fail-soft per object, never per run.** One unreachable object must not
  abort a whole clone/publish. (This repo has shipped that bug before; see the 08/14
  cache-layer review.)
- **Verify what you fetch.** Object ids are `sha256(ciphertext)[:12]`, so every object can
  be checked with no key and no trust in the host. Do it unconditionally.
- **`serve` binds `127.0.0.1` by default**, read-only, no directory listing, path-guarded
  (use `Vault__Path_Guard`), stdlib only — no new dependency.
- **Key material never lands in git.** Any one-repo work uses the canonical repo-side
  ignore set — `.sg_vault/local/`, `.sg_vault/backups/`, `.sg_vault_new/` (`07` §4). The
  `backups/` line is not optional: a keyed backup zip contains the vault key itself.
- **Verify before you write, on every read path (SP-1/I7).** A reader/clone must id-verify
  each `obj-cas-imm-*` object (`sha256(ciphertext)[:12] == id`) before writing it, and must
  **never** trust the manifest's `sha256` for content-addressed objects — the manifest is
  self-attested by the same host (SP-3).
- **Writes on a static transport raise**, they never silently no-op.
- **Never weaken the key rules shipped in `67c2ab6`**: `classify_key()` classifies by
  declaration, and an explicit prefix always beats the 64-hex heuristic.

## 4. Definition of done (every phase)

- [ ] `pytest tests/unit/ -n auto` green (currently **3653**; your phase adds tests)
- [ ] `pytest -m qa tests/qa -q` green (currently **102 passed / 20 skipped**)
- [ ] New code follows Type_Safe rules — no raw `str`/`int`/`dict` fields, enums for
      closed sets, a test class per class, round-trip test per schema
- [ ] Your phase's acceptance criteria in `05__implementation-phases.md` all pass
- [ ] No invariant in §2 weakened; if you had to touch one, say so explicitly in the PR
- [ ] User-facing strings match `02__commands-and-ux.md` (or the PR explains the change)
- [ ] Commit message states what was built and what was deliberately left out
- [ ] `CHANGELOG.md` in this pack has an entry for any spec file you changed

Integration tests need the 3.12 venv (see `CLAUDE.md` → Integration Testing).

## 5. Phase summaries — full detail in `05__implementation-phases.md`

| Phase | Build | Depends on | Size |
|---|---|---|---|
| **P0** | Tracked-wins in `Vault__Ignore`, **then** `.github/` added to the default ignore set (decision 17) | — | S |
| **P1** | `Vault__API__Static` — productionise the spike; `--transport` flag; transport reported in `vault info` | — | S |
| **P2** | `sgit publish` (the plaintext surface) + `manifest.json` | P1 | M |
| **P3** | `sgit vault serve` | — (P1 helps) | S |
| **P4** | `--visibility`, cover file, downgrade warning | P2 | M |
| **P5** | `sgit vault mirror` (custody) | P2 | S |
| **P6** | Bundles (`head-<commit>.zip`, per-commit deltas) | P2 | M |
| **P4b** | Published API docs — `api/openapi.json`, optional Swagger UI (CDN-pinned or bundled) | P2 | S |
| **P7** | The 6 invariants + 14 test cells as a suite | P1–P5 | M |
| **P8** | `sgit vault expand` — deployment-time expansion (**deferred, not v1**) | P2 | M |
| **P9** | `sgit vault attach` — bind a key to an existing checkout (**CI-blocking**) | — | S |

**Start with P0, then P1 and P3.** P0 is small and touches nothing else in this pack, but it
changes the ignore engine — land it before other phases start adding files to vaults. P1+P3
are then demonstrable value — clone from any GET host, browse any published folder locally.

**P0 has one non-negotiable ordering rule:** the tracked-wins exemption ships *before* (or at
minimum in the same commit as) the `.github` list entry. Reversed, it silently removes
already-tracked `.github/**` from existing vaults. See `12__accepted-risks.md` §6 — the code
references there are verified, not assumed.

## 6. What is NOT yours to decide

Raise these; do not resolve them in code:

- The seventeen decisions in `06__decisions-and-evidence.md` — **all signed off as of
  20 Aug**, so implement them as written rather than re-opening them. Where one is deferred
  (16, the signed head) or conditional (17's tracked-wins ordering), the condition is part of
  the decision, not a detail to optimise away. Accepted risks and their revisit triggers:
  `12__accepted-risks.md`.
- Anything that changes a **wire format** or a **key format** — those are cross-runtime
  contracts shared with SG/API and SG/Vault web.
- Anything that widens the plaintext surface beyond the allow-list in `01`.
- The loader's internal JavaScript — that is the Web team's. You emit the file; you do not
  author its behaviour.

## 7. When you get stuck

- **The spike disagrees with the spec** → the spec wins for *behaviour*, the spike wins for
  *proof it is possible*. Say which one you followed.
- **A test cell cannot pass** → check `06` first; two cells were re-scoped by measurement,
  and one (`sgit clone` with no key at all) is **structurally impossible** by design.
- **You need a live server** → don't. Use `Vault__API__In_Memory`, a `ThreadingHTTPServer`
  over a folder, or the local SG/Send test server (`tests/integration/conftest.py`).
- **Something looks like it needs a protocol change** → stop and write it up. That is the
  most valuable thing you can produce, and it is cheaper than discovering it after release.
