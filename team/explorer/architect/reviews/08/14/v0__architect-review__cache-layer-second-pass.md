# Architect Review — Cache Layer: Second Pass (Lifecycle & Boundary Values)

**Version:** v0
**Date:** 2026-08-14
**Role:** Architect (Explorer)
**Scope:** Full re-review of the cache layer after the post-implementation review (08/13) shipped. Two independent adversarial passes were run with different lenses — (a) state-machine/lifecycle interleavings across multiple actors, (b) data semantics and boundary values — plus empirical probes. Everything found in this round is **fixed in this round**, each with a regression test.

---

## 0. Executive Summary

The 08/13 review closed the single-copy, single-actor defects. This pass hunted the two places bugs were still hiding: **sequences across time and actors** (declare→rm→push, stale clone pushes, cross-clone duplicate declarations) and **values at the edge of the type system** (files past size caps, foreign objects, unpadded base64). It found two HIGH lifecycle defects, two HIGH boundary-crash channels, and a cluster of medium hardening gaps. All are fixed; unit 3615, QA 102, integration 63 all green.

The recurring shape from the 08/13 review held perfectly: every defect was a **silent no-op, silent rewrite, or silent delete inside a fail-soft layer** — and one new variant, *fail-soft at the wrong granularity* (one bad object silencing the whole layer).

---

## 1. Findings and fixes

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | HIGH | `cache rm` could never stick: the next push rediscovered the server copy via the D6 listing and resurrected it locally AND remotely | **Tombstones** (`Schema__Cache_Tombstones`, `.sg_vault/local/cache_tombstones.json`): rm records intent; push/repair issue the DELETE and clear the tombstone only after it lands |
| 2 | HIGH | Pre-pull `up_to_date` push reconciled from a **stale local head**, deleting/downgrading caches other clients just published; repair had the same flaw | Both now verify the server's named ref matches the local one first (`_server_named_commit_id`); mismatch → reconcile skipped with a "run `sgit pull`" warning, repair returns `stale_head` |
| 3 | HIGH | A >100 MB file overflowed `Safe_UInt__File_Size` in `build_pointer` → crashed repair, aborted the whole push reconcile forever | New `Safe_UInt__Cache_Size` (1 TB cap) on cache schemas; wire format unchanged (plain int) |
| 4 | HIGH | Fail-soft was all-or-nothing: one bad object (missing blob on a sparse clone, oversized value, foreign schema) silently killed reconcile for **every** cache on **every** push; repair crashed outright | Per-object try/except in both loops; `Vault__Cache_Blob_Missing_Error` + a server `blob_fetcher` so sparse clones heal what they can and *skip* (never delete) what they cannot |
| 5 | MED-HIGH | D4 unenforced across clients: value+pointer for one path were both maintained forever; kind replacement resurrected the old kind | `resolve_duplicates` moved into `Vault__Cache_Manager` and now runs in the push reconcile too; `cache add` tombstones the replaced kind |
| 6 | MEDIUM | Repair published server DELETEs for objects it merely could not parse — destroying a newer client's valid data | `classify_ciphertext`: `undecryptable` (garbage/foreign key) still cleaned up; `unparseable` (decrypts under our read_key — a key holder wrote it) skipped, never deleted |
| 7 | MEDIUM | A value cache whose file grew past the 1 MB cap crashed rebuild (or silently violated the batch budget between 1–7.5 MB) | Rebuild treats an over-cap value as unrepresentable → deleted with the orphan path (re-declare with `--pointer`); QA test proves the other caches still heal in the same push |
| 8 | MEDIUM | Reader: fresh blob pointer whose +1 read failed returned `fallback=False` with `content=None` — a contract-following Lambda would serve nothing | `fallback=True` whenever a resolved blob pointer yields no content |
| 9 | MEDIUM | Reader raised `binascii.Error` on valid-per-Safe-type but unpadded base64 (common in JS encoders) — in the "never raises" path | Guarded decode; malformed candidate degrades to a miss |
| 10 | MEDIUM | Dedup tie-break was mutability-blind (string sort preferred `muw`), stranding the snw-probing local fast path | Tie-break order: fresh → natural kind → **snw** → stable id |
| 11 | LOW | `--branch-only` silently skipped publishing declared caches; read-only clones could "successfully" declare unpublishable caches; `docs//readme.md` spellings derived unfindable ids; control-char paths crashed with a raw traceback | `cache_skipped` surfaced in push output; read-only clones rejected at `cache add`/`rm`; CLI normalisation collapses `//` and `/./`; clean error for control chars |

Also hardened while in there: a parseable object with an empty `path` is skipped (no identity → cannot be maintained), not executed as an orphan of `''`; dedup DELETEs are only issued for ids the server actually holds; a rebuilt object identical to the server's copy is no longer pointlessly rewritten (which also stops the silent v2→v1 format downgrade for foreign objects that happen to parse).

## 2. Semantics that changed on purpose

- **`cache rm` on an undeclared path is no longer a no-op.** It records tombstones for both kind ids, because the declaration may live only on the server (another clone's). This is what lets any clone retire any cache. Message: "removal recorded".
- **A stale clone's `sgit push` may print a warning and do nothing to caches.** That is the fix working: reconciling from behind is how caches got destroyed.
- **`cache repair` refuses to run from behind the server** (`stale_head`) — pull first.

## 3. Interop notes for the SG/Vault (browser) mirror

Two findings are contract-relevant, not just CLI bugs, and belong in the browser brief when it is written: (a) emit **padded** canonical base64 in `value_b64`; (b) `content_hash` is the 12-hex prefix, `None` (not `""`) when absent for pointers — a mirror emitting `""` where the CLI emits `null` causes a rewrite ping-pong between clients. Tombstones are deliberately **local-only state**, not wire format: the wire-level removal is an ordinary DELETE, so no contract change and nothing for the server or browser to learn.

## 4. Deliberately not fixed (documented)

- `Safe_Str__Content_Type` sanitises MIME parameters (`; charset=` → `__charset_`). Idempotent and internally consistent, so no drift or rewrite loops — but a mirror must replicate the exact substitution. Flagged for the interop vectors rather than changed, since the type is shared with tree entries.
- F5 (muw CAS writes) and F7 (presigned pointer resolution >4 MB) remain open as before.
- Cross-clone kind *preference* is last-writer-loses when both are fresh (natural kind wins deterministically). Switching kind from a clone that never held the old declaration requires `rm` + push + `add`.

## 5. The lesson, again, sharpened

08/13's rule was "fail-soft layers need positive-outcome tests". This round adds two corollaries now encoded in the suites: **fail-soft must be per-object** (an aggregate try/except converts one bad input into a permanently degraded subsystem with a one-line warning nobody reads), and **every discovery mechanism is a resurrection mechanism** (D6's listing-as-registry is what healed caches across clones AND what un-deleted them; any folder-as-registry design needs a removal intent that outlives the object).

---

*Suites after fixes: unit 3615 passed; QA 102 passed / 20 skipped; integration 63 passed against the real in-process SG/Send server (including rm-over-HTTP and the stale-clone guard). Fixed in the same branch as the 08/13 round.*
