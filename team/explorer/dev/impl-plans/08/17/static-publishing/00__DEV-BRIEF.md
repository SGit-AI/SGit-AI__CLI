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

Skim only as needed: `02__commands-and-ux.md` (exact user-facing strings),
`03__flows.md`, `06__decisions-and-evidence.md`. If you are on P2 read `07__publish-target.md`
in full, and on P4b read `08__api-docs.md` in full — both carry acceptance criteria.

## 2. The six rules that override convenience

These are the design's actual claims. A change that breaks one is wrong even if the tests
pass, so if you find yourself weakening one, stop and raise it instead.

1. **Published ciphertext is byte-identical regardless of destination.** No
   destination-specific branch in the publish step. Ever.
2. **The key never reaches a server.** Never in a path, never in a query. Fragment or
   file only.
3. **A keyless client can take custody** — mirror/copy a vault it cannot read. This is
   why `manifest.json` is mandatory.
4. **The loader is byte-identical everywhere.** Always emitted from sgit's bundled
   template, never from vault content.
5. **Plaintext is emitted only where the key is published.** Enforced by the command, not
   by documentation. The failure is silent and permanent (git history).
6. **Publishing never changes the vault.** The output folder may not be inside the work
   tree, nor contain it — otherwise the next `push` swallows the output and the store
   doubles on every cycle. Rule and messages: `07__publish-target.md`.

## 3. Non-negotiable implementation constraints

- **The plaintext surface is a fixed allow-list in code.** Never derive it by matching
  vault content (no "any file called `index.html`"). If it were pattern-derived, anyone
  who can write to the vault could move a file into the plaintext surface by naming it.
  Every emitted plaintext file is also recorded, with its `sha256`, in `manifest.json`.
- **Reads must stay fail-soft per object, never per run.** One unreachable object must not
  abort a whole clone/publish. (This repo has shipped that bug before; see the 08/14
  cache-layer review.)
- **Verify what you fetch.** Object ids are `sha256(ciphertext)[:12]`, so every object can
  be checked with no key and no trust in the host. Do it unconditionally.
- **`serve` binds `127.0.0.1` by default**, read-only, no directory listing, path-guarded
  (use `Vault__Path_Guard`), stdlib only — no new dependency.
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

Integration tests need the 3.12 venv (see `CLAUDE.md` → Integration Testing).

## 5. Phase summaries — full detail in `05__implementation-phases.md`

| Phase | Build | Depends on | Size |
|---|---|---|---|
| **P1** | `Vault__API__Static` — productionise the spike; `--transport` flag; transport reported in `vault info` | — | S |
| **P2** | `sgit publish` (ciphertext only) + `manifest.json` | P1 | M |
| **P3** | `sgit vault serve` | — (P1 helps) | S |
| **P4** | `--visibility`, cover file, invariant-5 enforcement | P2 | M |
| **P5** | `sgit vault mirror` (custody) | P2 | S |
| **P6** | Bundles (`head-<commit>.zip`, per-commit deltas) | P2 | M |
| **P4b** | Published API docs — `api/openapi.json`, optional Swagger UI (CDN-pinned or bundled) | P2 | S |
| **P7** | The 6 invariants + 14 test cells as a suite | P1–P5 | M |

**Start with P1 and P3.** Together they are demonstrable value — clone from any GET host,
browse any published folder locally — and they commit to nothing in the publish protocol
that is still being decided.

## 6. What is NOT yours to decide

Raise these; do not resolve them in code:

- The ten open decisions in `06__decisions-and-evidence.md` (canonical layout, loader
  source-of-truth, key-file vs pointer, serve bind default, default visibility, ship order,
  Swagger UI delivery mode, whether the spec is always emitted, default publish target,
  first-party asset origin).
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
