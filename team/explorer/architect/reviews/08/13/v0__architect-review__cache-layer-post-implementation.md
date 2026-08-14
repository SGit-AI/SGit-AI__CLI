# Architect Review — Cache Layer: Post-Implementation

**Version:** v0 (repo tag `v0.15.0` + cache branch)
**Date:** 2026-08-13
**Role:** Architect (Explorer)
**Scope:** Adversarial re-review of the shipped cache layer (Phases 1–4, commits `31a869a..5ba0591`) against the plan it implements (`contracts/08/12/v0.3__architecture__cache-layer-decisions.md` D1–D10 and the wire-format contract). Question asked: what did the plan promise that the code does not deliver, and what does the code do that the plan never sanctioned?

**Method:** re-read of every cache-layer file plus empirical probes of the suspicious spots (typed-boundary behaviour, unicode paths, size limits) rather than code-reading alone. The live API surface at `send.sgraph.ai/api/openapi.json` was fetched to confirm the zero-server-change claim (§4).

---

## 0. Executive Summary

The implementation matches the plan closely: all ten decisions D1–D10 are present in code, all four phases shipped with tests, and the three bugs found during development (up-to-date push not publishing, `cat` serving pre-commit content, D6 healing inert) were fixed with regression tests. This pass found **one HIGH defect that had survived everything** — unicode paths silently self-destruct their caches — plus two hardening gaps, all fixed in this round, and three accepted/deferred items now stated explicitly.

**Verdict: SHIP.** The remaining open items (F5 muw semantics, F7 large-blob pointer reads) are documented limitations, not defects, and neither affects the snw-only surface the CLI exposes.

---

## 1. Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| F1 | HIGH | Unicode paths sanitised on storage → cache self-destructs on next push | **FIXED** |
| F2 | MEDIUM | `--value` accepted unbounded file sizes → object cannot fit server batch body | **FIXED** |
| F3 | LOW | No path normalisation at the CLI boundary (`media/` ≠ `media` ≠ `./media`) | **FIXED** |
| F4 | — | `Safe_Str__Base64_Data` capacity (flagged unverified in Phase 1) | **VERIFIED OK** (10 MB) |
| F5 | MEDIUM | `muw` mutability is representable but its CAS write semantics are unimplemented | **OPEN — documented v1 limitation** |
| F6 | INFO | `list_files('bare/cache/')` on every push (one call, cache-less vaults included) | **ACCEPTED** (the price of D6) |
| F7 | LOW | Reader resolves pointer blobs via plain `api.read` — no presigned path for >4 MB blobs | **OPEN — falls back safely** |
| F8 | INFO | `cache add` is not gated on read-only clones (declares locally; push impossible) | **ACCEPTED** (harmless) |

### F1 — HIGH: unicode paths self-destructed their caches (fixed)

`Schema__Cache_Value.path` used `Safe_Str__File_Path`, which is a **sanitiser**: it rewrites anything outside `[a-zA-Z0-9/\_.\- ]`. Reproduced end to end:

```
declare cache on docs/café-notes.md   → stored path becomes 'docs/caf_-notes.md'
next sgit push                        → flat.get('docs/caf_-notes.md') = None
                                      → classified as orphan → cache DELETED
```

Three simultaneous failures from one root cause: the stored path violated the contract's byte-identical rule (§4), the reader's collision guard rejected every legitimate read (`stored ≠ requested`), and the reconcile *deleted* the cache it was supposed to maintain. Silent in all suites because every test path was ASCII.

**Fix:** new `Safe_Str__Cache_Path` — MATCH-mode **validation** (any character except control chars, `trim_whitespace=False`), never rewriting. The stored path is an identity, not display text. Regression test drives the full declare→push→read cycle with `café` in the path. The general lesson is recorded below (§3).

### F2 — MEDIUM: unbounded `--value` (fixed)

Auto-selection respected the 4 KB threshold, but explicit `--value` accepted any size. A 50 MB file would produce a ~67 MB base64 field inside one batch op — over the 4 MB batch budget and Lambda's ~6 MB body limit, failing at push time with an opaque server error. Now refused above a 1 MB hard cap with a message directing to `--pointer`; oversized files with no flags already defaulted to pointer (test added).

### F3 — LOW: CLI path normalisation (fixed)

`sgit cache add media/` and `sgit cache add media` derived **different ids**, so a user could declare a cache and then fail to remove it. Normalisation (`./` prefixes, trailing slashes, `\`→`/`) now happens at the CLI boundary only — the programmatic layers deliberately keep raw-path identity per the contract.

### F5 — MEDIUM, OPEN: `muw` is a label, not yet a semantics

The id grammar, schemas and reader all handle `muw`, but the write path always issues plain `WRITE`; the design's `muw ⇒ WRITE_IF_MATCH` CAS discipline (D3 of the original per-path design) is unimplemented. This is safe **because nothing can currently create a muw object**: the CLI has no flag for it and defaults are snw. Recorded as the v1 boundary: *snw is implemented; muw is reserved wire-format space.* Implementing it means threading the prior object hash into the reconcile batch — deferred until a genuine multi-writer consumer exists.

### F7 — LOW, OPEN: large-blob pointer resolution

`Vault__Cache_Reader` resolves a blob pointer with plain `api.read`, which Lambda-backed servers may 502 above ~4 MB. The failure is safe (content stays None, `fallback=True`) but the fast path silently degrades for large files. Fix when needed: honour the `large` flag with `presigned_read_url`, as `sparse_cat` already does.

---

## 2. Plan-vs-implementation conformance

| Decision | Implemented | Note |
|---|---|---|
| D1 storage layout | ✅ `bare/cache/{value,pointer}/` | |
| D2 kind-in-domain derivation | ✅ + interop vectors asserted | |
| D3 `cch-pid-` grammar | ✅ `Safe_Str__Cache_Id` | |
| D4 one object per path | ✅ CLI replace + repair dedup | |
| D5 folder-as-registry | ✅ no manifest anywhere | |
| D6 reconcile from server listing | ✅ **after the fix** — was inert until the multi-clone tests | |
| D7 deliberate rekey drop | ✅ documented in move step | |
| D8 command surface | ✅ add/rm/status/repair | |
| D9 Safe_*-typed schemas | ✅ (enums upgrade, contract reconciled) | F1 corrected the one wrong type choice |
| D10 direct write, never object store | ✅ + regression test documenting why | |
| §7 read protocol | ✅ 1 RT value / 2 RT blob pointer / fallback-always | F7 caveat |
| §4.2 read_key-only capability | ✅ asserted by detached-reader tests | |
| v0.2 §4 reconcile-all (not diff-only) | ✅ reconcile covers every discovered object | |

Sanctioned deviations: enums instead of `Safe_Str` for closed sets (contract updated at the time); `cat`'s local-head freshness rule vs the reader's server-ref rule (both documented — they answer different questions).

---

## 3. The pattern worth keeping

Every bug this feature produced — publish-on-up-to-date missing, `cat` serving stale content, D6 inert, F1 — shared one shape: **a silent no-op or silent rewrite inside a fail-soft layer.** Fail-soft is the right design for a derived cache, but it converts bugs from loud to invisible, so the tests must assert *positive* outcomes (object updated, content followed, survives push), never merely "no error". The multi-clone scenario and the unicode regression exist precisely because single-copy ASCII tests could not see these failures. Recommendation for QA: any future fail-soft path gets a companion test that proves the action *happened*, not that it didn't raise.

Second lesson (F1): in this codebase Safe_Str types are sometimes sanitisers and sometimes validators. **Identity fields must never use a sanitising type** — a rewrite of an identity is corruption. Worth a line in CLAUDE.md's Type_Safe rules at the next touch.

---

## 4. Zero-server-change claim — verified against the live spec

`send.sgraph.ai/api/openapi.json` exposes everything the cache layer uses and nothing it lacks: `PUT/GET/DELETE /api/vault/{write,read,delete}/{vault_id}/{file_id}`, `POST /api/vault/batch/{vault_id}`, `GET /api/vault/list/{vault_id}?prefix=`, presigned read. `file_id` is an unconstrained path parameter, so nested `bare/cache/value/…` ids ride through. The companion guide (`team/explorer/dev/guides/08/13/`) turns this into an executable checklist against the live server.

---

## 5. Hand-Off

**To Dev (done in this round):** F1–F3 fixes + regressions (`Safe_Str__Cache_Path`, value cap, normalisation).
**To Dev (deferred, tracked here):** F5 muw CAS writes; F7 presigned pointer resolution.
**To QA (binding):** the §3 rule — positive-outcome tests for every fail-soft path.
**To Historian:** picks up automatically.

---

*Verified against the working tree at the commits in the header; unicode failure and both capacity checks reproduced empirically before fixing. Suites after fixes: unit 3583 passed, QA 89 passed / 20 skipped.*
