# KNOWN ISSUES — Living Register

The single page every assessment run reads before looking for anything new.
One entry per issue: what it is, its status, and where the full story lives.
**Updated only by conductor runs and humans.** An assessment finding that
matches an entry here is not a new finding — unless the evidence changed.

Statuses: **open** (acknowledged, unfixed) · **accepted** (deliberate
decision, will not fix as-is) · **scheduled** (fix planned, gated on
something) · **historical-unverified** (from an old register; current
status unknown — verifying these IS assessment work).

Last updated: 2026-08-14 (seeded by the cache-layer second-pass session).

---

## Security

| ID | Entry | Status | Source |
|----|-------|--------|--------|
| KI-SEC-01 | **48-bit object IDs**: collision *consequence* fixed (`Vault__Object_Collision_Error`, no silent overwrite); collision *probability* unchanged. Widening to 256-bit is a coordinated cross-runtime format bump + whole-vault migration, bundled with the next breaking schema change. | scheduled | `team/explorer/architect/reviews/08/13/v0__security-response__external-review-remediation.md` §3 |
| KI-SEC-02 | **Deterministic tree encryption leaks equality relationships** (never plaintext names/sizes/content — the "filenames" visible server-side are obj-ids of encrypted content). Required for CAS dedup. | accepted | security response §7.1 |
| KI-SEC-03 | **read_key stored on disk for read-only clones** (`clone_mode.json`). Dinis decision; AppSec F07. | accepted | `sgit_ai/schemas/Schema__Clone_Mode.py` comment |
| KI-SEC-04 | **PKI is classical-only** (ECDSA P-256, RSA-4096). Vault confidentiality is AES-256 (quantum-resistant); signatures/messaging are the roadmap item. | open | security response §7 |
| KI-SEC-05 | **Server-side simple-token exposure** (historical tokens, mint paths, logs) is owned by the SG/Send team; advisory delivered. CLI side removed clean-cut — old token vaults are unreadable by current CLI. | accepted | security response §1 |
| KI-SEC-06 | **No lint/type/dependency/security gate in CI**; known Ruff (~185) and Bandit (~23 medium) findings; ~158 broad `except Exception` handlers. | open | security response §7 |
| KI-SEC-07 | **PyPI/DockerHub publish policy**: publishing from `dev` pushes was disabled 08/13 in-repo; release actions SHA-pinned. Residual: pin freshness is manual. | accepted | `.github/workflows/ci-pipeline.yml` |

## Resilience / correctness (cache layer)

| ID | Entry | Status | Source |
|----|-------|--------|--------|
| KI-RES-01 | **F5 — `muw` mutability is reserved wire-format space, not semantics**: CAS (`WRITE_IF_MATCH`) writes unimplemented; nothing can currently create a muw object. | open | `team/explorer/architect/reviews/08/13/v0__architect-review__cache-layer-post-implementation.md` F5 |
| KI-RES-02 | **F7 — pointer resolution for >4 MB blobs** uses plain `api.read` (may 502 on Lambda backends); degrades safely to `fallback=True`, never wrong. Fix: presigned reads, as `sparse_cat` does. | open | same review, F7 |
| KI-RES-03 | **Cross-clone kind preference is last-writer-loses when both fresh** (D4 dedup keeps the natural kind deterministically). Switching kind from a clone that never held the old declaration requires `rm` → push → `add`. | accepted | `team/explorer/architect/reviews/08/14/v0__architect-review__cache-layer-second-pass.md` §4 |
| KI-RES-04 | **Repair/push skip decryptable-but-unparseable cache objects** (assumed newer-schema); they persist until a newer client handles them. Deliberate — deleting them would destroy another client's data. | accepted | second-pass review #6 |

## Interop (browser/SG-Vault mirror contract)

| ID | Entry | Status | Source |
|----|-------|--------|--------|
| KI-INT-01 | **`Safe_Str__Content_Type` sanitises MIME parameters** (`; charset=` → `__charset_`). Idempotent, internally consistent; a byte-for-byte mirror must replicate the exact substitution. Needs an interop test vector. | open | second-pass review §3–4 |
| KI-INT-02 | **Mirror clients must emit padded canonical base64** in `value_b64` and `null` (not `""`) for absent pointer `content_hash` — otherwise rewrite ping-pong between clients. Needs contract vectors. | open | second-pass review §3 |

## Historical register (2026-03-20) — statuses unverified

`library/sgit-ai/briefing-packs/03/20/10__KNOWN_ISSUES.md` lists BUG-001
(push silent partial failure), BUG-002 (deletion resurrection on pull),
BUG-003 (false conflicts after pull) and more, from five months ago. Much of
that code has been rewritten since (push checkpointing, batch CAS, merge
state). **The bugs role verifies these each run** and this register is
updated with confirmed-fixed / still-open verdicts.

| ID | Entry | Status |
|----|-------|--------|
| KI-HIST-01 | March-tracker bugs BUG-001..003 and remainder of that page | historical-unverified |

## Documentation / UX

| ID | Entry | Status | Source |
|----|-------|--------|--------|
| KI-DOC-01 | `Alpha` PyPI classifier is deliberate — project is pre-1.0. | accepted | security response §7 |
| KI-UX-01 | `cache rm` on an undeclared path prints "removal recorded" (records tombstones) — deliberate, not a bug. Stale-clone pushes may print "reconcile skipped — run `sgit pull`" — that is the stale-head guard working. | accepted | second-pass review §2 |

---

## How to update this page (conductor / humans only)

- New confirmed finding the team decides to defer → add with status **open**.
- Deliberate decision not to fix → **accepted**, with the source of the decision.
- Fixed → **remove the row** and note the removal in that run's assessment
  pack (the runs history is the audit trail; this page stays current-state only).
- Keep entries one row each; the Source column carries the depth.
