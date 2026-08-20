# Debrief — static-publishing implementation (P0–P7, P9)

**Date:** 2026-08-20
**Branch:** `claude/sgit-cli-review-rxll54` (based on `dev` @ `6c3e343`, which carries the pack)
**Spec:** `team/explorer/dev/impl-plans/08/17/static-publishing/` (r14 at start, **r17** at end)
**Suites:** `pytest tests/unit/ -n auto` → **3812 passed** (from a 3653 baseline) · `pytest tests/qa -q` → **122 passed / 20 skipped** (from 102/20)

> **Update (post-review).** The architecture session reviewed this work
> (`…/architect/reviews/08/20/v0__review__static-publishing-implementation.md`) and raised
> two High integrity findings plus four smaller ones. I reproduced both High findings
> independently, fixed all six (pack r16), and then closed the deeper one at the root by
> rewriting `sgit vault move` (pack r17). **§6 below is therefore resolved** — see §6a.
> Full reply: `…/static-publishing/responses/08/20/v0__response__implementation-review.md`.

---

## 1. What this session did, in order

1. **Reviewed the CLI in depth** (entry points, vault model, crypto tiers, transport seam,
   the 10-step clone workflow, the push/commit/status pipeline, the ignore engine).
2. **Read the handoff pack and verified its code claims line-by-line** before writing any
   code. Almost every claim checked out exactly; the ones that didn't became the spec
   defects in §5.
3. **Implemented every v1 phase** of the pack, in the pack's order, one commit per
   phase-group, tests green at every commit.
4. **Corrected the spec files** where execution proved them wrong (pack CHANGELOG r15),
   per the pack's own rule that stale text is a bug to report.

## 2. What landed (by commit)

| Commit | Phases | Summary |
|---|---|---|
| `3ab0535` | **P0** | Tracked-wins in the ignore engine, then `.github` in `ALWAYS_IGNORED_DIRS`. Ignore rules now govern **untracked files only** (git's rule): the vault head's path set loads into `Vault__Ignore` via the new `Vault__Head_Paths`, across all ~9 work-tree walks. One-time migration notice; new **`sgit vault ignore --apply <folder>`** escape hatch (one visible commit, work tree untouched). The maintainer's "no side effects on existing vaults" condition is a regression test. |
| `117608e` | **P1 + SP-1** | **`Vault__API__Static`** — clone/fetch/pull from any GET host or folder; both layouts sniffed once, sticky; writes raise `Vault__Read_Only_Transport_Error`; only HTTP 404 means absent — a dead host raises **naming the host** (F5); request recording for the I2 assertion. **`Vault__API__Auto`** resolves `--transport auto` (folder → local; http flips to static on 404/405/501, announced, never silent). Transport reported in clone output and `sgit vault info`; SP-6 warning for a private key over plain `http://`. **SP-1/I7:** every download path writes through `Vault__Verified_Write` — id-verify *before* the write, path-guarded, per-object fail-soft; checkout and the commit walk tolerate a skipped object. Includes a real 5 MB fixture for the presigned large-blob path. |
| `472e995` | **P2, P3, P4, P4b, P6** | **`sgit publish`** — the plaintext surface only (loader byte-identical for every vault, cover, manifest; key file only at `public`); no ciphertext, no target argument, deterministic, read-key-only capable. **Visibility** per-clone (decision 5), public confirmation + git-history note, downgrade warning (R3). **`sgit vault serve`** — loopback, GET/HEAD only, no listing, path-guarded virtual `bare/` route (SP-8), Host check (SP-9), auto-publish when absent/stale (keyless refs compare). **API docs** — `api/openapi.json` from the manifest enumeration; CDN mode with all five required attributes incl. the mandatory CSP (SP-11); bundled mode fetch-verifies against the same SRI pins and fails closed. **Bundles** — `ZIP_STORED`, immutable names, deterministic, delta union reconstructs `bare/data` exactly, id-verified extraction. |
| `002b05e` | **P5, P9, P7** | **`sgit vault mirror`** — keyless custody; SP-3 (content-addresses recomputed, manifest hashes never authority for them), SP-8 (path-guarded file_ids, bounded count/size, duplicate rejection), `--verify`, the honest no-listing failure, writes no key file. **`sgit vault attach`** — validate-first (`Nothing written.` on a wrong key), mode-exclusive (F6a), `Schema__Clone_Mode`-exact (F6b); retires the three tabletop lab stand-ins. **QA Scenario 4** — all seven invariants (I1–I7) + matrix cells 1, 2, 3, 4, 7, 9, 11, 13 and the **cell-14 fork acceptance test** (clone from a published target → rekey → republish → read back with the new key). Decision 13's canonical repo-side gitignore set ships as `Vault__Repo_Ignore.CANONICAL_REPO_GITIGNORE`, asserted literally; `sgit vault backup` warns in a git work tree missing the `backups/` line. |
| `9873c37` | **r15** | Spec-pack corrections + pack CHANGELOG r15 + repo CHANGELOG entries. |

New user-facing commands: `sgit publish`, `sgit vault serve`, `sgit vault mirror`,
`sgit vault attach`, `sgit vault ignore`, and the `--transport` flag on the shared
network arguments.

## 3. Design decisions made during implementation (all recorded in r15)

- **Tracked-wins lives inside `Vault__Ignore`**, not at a call site. The pack suggested
  patching one call site; the prune is actually repeated across ~8–9 walks, so the
  exemption is central and every walk loads the head's path set in one line.
- **SP-1's verification got a post-move fallback** (see §6 — this is the one item that
  needs an architecture decision): sha256 of the ciphertext first; on mismatch, accept
  only if the object still AES-GCM-authenticates under the reader's key. Keyless
  consumers (mirror) stay strict and report such objects as *host-attested*, never
  *verified*.
- **`Vault__Static_Server` lives in `core/serve/`**, not the spec's `network/serve/` —
  the repo's layer rules forbid network → storage imports and `Vault__Path_Guard` lives
  in storage.
- **Transport error classes live in the network layer** (`Vault__Transport_Errors`),
  re-exported from `core/Vault__Errors` so callers find every vault error in one place —
  same layering constraint.
- **No `Schema__OpenAPI_Document` Type_Safe class** (P4b file list): OpenAPI is an
  externally-specified nested-map format; the document is generated directly from the
  same enumeration that feeds `manifest.json`, so it cannot drift. Raised, not hidden.
- **The docs page's UI init lives in a same-origin `init.js`** — the mandatory CSP
  (SP-11) allows no inline script, which the spec's own mockup would have violated.
- **`cover.json`'s `updated` derives from the head commit's timestamp**, never wall
  clock — otherwise P2's "publishing twice is byte-identical" criterion is unsatisfiable.
- **I6 excludes exactly one file:** recording the clone's visibility choice
  (decision 5) necessarily touches `.sg_vault/local/config.json` (never-pushed local
  state). Everything else is byte-identical across a publish, asserted by tree hash.

## 4. Spec defects found by execution (fixed in the pack, r15)

1. **P0's cited call site was wrong.** `Vault__Sync__Push.py:771-773` is the pre-push
   `.conflict` scan; push never walks the work tree for content. The deletion-producing
   walk is `Vault__Sync__Base._scan_local_directory` (status/commit/pull), duplicated in
   branch-switch, stash, revert, merge, diff and bare.
2. **SP-1's "verify unconditionally" is unbuildable against shipped `sgit vault move`**,
   which re-encrypts every object in place *keeping its old id* (`store_at` deliberately
   breaks the CAS invariant). A moved vault has zero objects that hash to their ids; the
   move test suite caught the conflict immediately. Shipped `fsck` has the same latent
   inconsistency (it would report every object of a moved vault corrupt).
3. **`00` §4's QA command didn't produce its stated numbers** — `pytest -m qa tests/qa`
   selects only ~48 tests (most QA tests are selected by path, not marker); the plain
   path invocation matches the counts.
4. **`02` §6 carried a pre-r5 stale row** ("plaintext warning on a vault-supplied
   index.html") describing a warning that cannot exist post-r9.
5. **`07` §6 mixed P8 acceptance criteria into P2**, and claims a manifest fact
   ("records which file ended up at the root") that only expansion-time code could
   record.
6. **The spec's `network/serve/` placement violates the repo's own layer rules.**

## 5. What is missing / deliberately not done

| Item | Status | Why |
|---|---|---|
| **P8 — `sgit vault expand`** | Not built | Deferred by decision 11; explicitly not v1. Cells 6 and 12 depend on it. |
| **Matrix cells 5 & 10** (real Pages round-trip; run-time ACAO assertion) | Not built | Need a real remote host — integration scope, plus the "still owed to a real-GitHub run" items from tabletop 11 (Pages propagation timing, secret masking in logs, measured provider headers). |
| **Cell 8** (stored-key returning visitor) | Not built | Web team's (loader behaviour). |
| **Real loader JavaScript** | Placeholder | The emitted template is byte-identical everywhere and documents the Web team's contract (01 §7: key discovery, classify-by-declaration, fragment hygiene, fetch paths); the behaviour is theirs to author. Swapping the template in is a one-constant change. |
| **Decision 15's workflow generator** (`sgit publish setup github`) | Not built | Decided but in no phase's file list. `templates/github-pages.yml` remains the canonical copy. |
| **Read-write `attach` doesn't create a clone branch** | Known gap | Matches the tabletop lab semantics: status/publish/serve all work (tested); `sgit commit` after a read-write attach needs a branch-registration follow-up. |
| **Integration suite not run** | Environment | Needs the Python 3.12 venv + `sgraph-ai-app-send`, unavailable in this container. Nothing in the diff touches the live-API wire format. |
| **Decision 16 (signed monotonic head)** | Deferred by decision | Still required before private-read or CI tiers are called "supported". |

## 6. The item that needed an architecture decision — RESOLVED (see §6a)

*(Original text, kept for the record.)* **SP-1 × `sgit vault move` residual gap.** The
implemented rule (sha256 first, GCM fallback under the reader's key) keeps moved vaults
working and keeps garbage out — a host without the key can forge nothing. But because move
reuses ids, an attacker who can serve bytes can swap one *valid* ciphertext under *another
object's name* and the GCM fallback accepts it (both decrypt under the same read key).

**What the review corrected.** I scoped this to moved vaults; it was not. The fallback fires
on **any** clone that holds a key, so the swap worked on a never-moved vault — reproduced by
the reviewer and again by me. My QA I7 cell missed it because it fed garbage bytes that never
engaged the fallback. That was the most valuable thing the review found.

## 6a. How it was closed — `move` rewrites object ids (option 3)

The maintainer chose the root fix over gating the fallback. `sgit vault move` now performs a
bottom-up topological rewrite of the object graph instead of re-encrypting in place:

- **Types come from reachability** (refs → commits → trees → entries), never from sniffing
  the plaintext — a blob whose content is JSON with a `schema` key would otherwise be
  misparsed as a tree.
- **Order:** blobs → trees (children first) → commits (parents first), each re-encrypted
  under the new key and stored at its **recomputed** id, with every reference remapped
  (merge commits' second parents included); refs repointed at the rewritten head.
- Undecryptable objects are carried verbatim at their existing id (still their true content
  address); unreachable orphans get new ids and stay unreachable.

**Result:** the content address holds for a moved vault exactly as for a fresh one, so the
GCM fallback was **deleted** — verification is now strict for keyed and keyless callers
alike. Verified end-to-end: the swap is refused and never reaches the working copy; a moved
vault has zero objects failing their content address and clones cleanly.

**Two things this also bought:**
- **Unlinkability, which move was supposed to provide.** Keeping ids meant a vault and its
  moved copy shared every `obj-cas-imm-*` id — a trivial correlation for anyone who saw both
  stores. No id survives a move now.
- **`store_at`'s CAS-breaking mode has no caller left in move**, so "the content address is
  never broken" is true system-wide again — the property that made SP-1 clean to begin with.

**A tested expectation was deliberately reversed** and is worth a second opinion:
`test_Vault__Sync__Move__Object_IDs.py` (and one test in `test_Vault__Sync__Move.py`)
asserted that pre-move ids must survive — the exact behaviour that caused the gap. They now
assert the intent behind them (no *content* lost: work tree identical, object count
preserved, one sentinel per named branch) plus the new invariant (every object verifies
against its own id, no id reused).

**Still open, and genuinely the maintainer's call:** migration for vaults already moved by an
older sgit. Their objects keep the old un-addressed ids, so a strict reader refuses them —
the clone diagnostic names the remedy (re-run `sgit vault move` to normalise), but that is a
manual step. If such vaults exist in the wild, a detect-and-normalise path may be worth
adding before release.

## 7. Where everything is

- **Code:** `sgit_ai/network/api/Vault__API__Static.py`, `Vault__API__Auto.py`,
  `Vault__Transport_Errors.py`, `sgit_ai/network/assets/Swagger_UI__Assets.py`,
  `sgit_ai/storage/Vault__Verified_Write.py`, `sgit_ai/core/Vault__Head_Paths.py`,
  `Vault__Repo_Ignore.py`, `sgit_ai/core/serve/Vault__Static_Server.py`,
  `sgit_ai/core/actions/{publish,mirror,admin,lifecycle}/…`,
  `sgit_ai/cli/CLI__{Publish,Serve,Mirror}.py`, schemas under `sgit_ai/schemas/publish/`.
- **Tests:** `tests/unit/network/api/test_Vault__API__Static.py`,
  `tests/unit/core/serve/`, `tests/unit/core/actions/{publish,mirror,lifecycle}/`,
  `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py`,
  `tests/qa/test_QA__Scenario_4__Publishing_Matrix.py`.
- **How to test everything:** `team/explorer/dev/guides/08/20/testing-static-publishing.md`.
- **Change control:** pack `CHANGELOG.md` r15; repo `CHANGELOG.md` → `[Unreleased]`.
