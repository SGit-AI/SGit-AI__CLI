# Response to the implementation review (A1–A6)

**Responding to:** `team/explorer/architect/reviews/08/20/v0__review__static-publishing-implementation.md`
**Branch:** `claude/sgit-cli-review-rxll54`
**Date:** 2026-08-20 · **Suites after fixes:** 3811 unit / 121+20 qa, green

The review is accurate. I reproduced both High findings independently before touching code —
the object swap on a never-moved vault (A1) and the `.git/hooks/pre-commit` write into the
victim's directory (A2) — and all six findings are now addressed. Verdicts below.

## A1 — SP-1 bypassable on every vault → FIXED (visible); closure still a decision

Confirmed and important: the review is right that the fallback is unconditional, not
move-scoped. My debrief §6 under-scoped it. Shipped the review's option 1:

- `Vault__Verified_Write` now returns a three-way verdict (`verified` / `authenticated` /
  `refused`), adopting the mirror's vocabulary as the review suggested.
- Clone and pull/fetch accumulate `authenticated` objects and print a **once-per-run
  warning** naming the substitution risk.
- The QA I7 cell gained the swap case (`test_I7_object_swap_is_not_silent`); the old cell used
  garbage bytes that never engaged the fallback, exactly as the review noted.

**Still needs a decision (not mine):** the deeper closure — option 2 (record a move marker so
the fallback only fires for moved vaults) or option 3 (move rewrites object ids). Both touch
either move's on-disk state or the wire contract, so they belong with decision 16. The hole is
no longer silent, which was the review's "ship now regardless."

## A2 — structural dirs not exempt from tracked-wins → FIXED

Confirmed (`.git/hooks/pre-commit` written into a fresh clone). Fixed at two layers:

- **Storage:** `Vault__Path_Guard.VAULT_PROTECTED_DIRS` = `.sg_vault`, `.sg_vault_new`,
  `.sg_vault_old_*`, `.git`, with `is_protected(rel_path)` checking every segment.
- **Ignore engine:** structural paths are refused *before* the tracked-wins exemption, so a
  head that tracks them cannot grandfather them. `.github` grandfathering is untouched — it is
  a preference, not a structural invariant, which is the whole point of P0.
- **Checkout:** both `Vault__Sub_Tree.checkout` and `Vault__Sync__Base._checkout_flat_map`
  (the pull/branch-switch path) skip writing any entry under a protected segment.
  `Vault__Path_Guard` genuinely cannot help here, as the review said — these paths do not
  escape the destination.

Note on "side effects on existing vaults" (the P0 condition): dropping already-tracked
`.git`/`.sg_vault` entries from a head on the next commit is correct self-healing, not the
data-loss P0 guards against — those paths are never legitimate content. Only real content
(`.github` workflows) is grandfathered.

## A3 — `--bind` disabled the Host check → FIXED

The check now stays on when widened. Rule: allow loopback names and any IP-literal Host
(DNS rebinding fundamentally needs a *domain name* in Host), plus the exact configured bind;
refuse domain-name Hosts. That defends the operator's browser on `0.0.0.0` while still
allowing legitimate LAN access by IP.

## A4 — local static reads not path-guarded → FIXED

Guarded inline in `Vault__API__Static._location` (the network layer may not import the
storage-layer `Vault__Path_Guard`): a local `file_id` that resolves outside the served root
returns absent. Read-only, but now symmetric with the mirror's write-side SP-8 guard.

## A5 — non-404 raised a bare `RuntimeError` → FIXED

Non-404 HTTP status is now a typed `Vault__Static_Object_Error` and fails soft per object in
`batch_read` (recorded in `failures`, run continues); a dead host still raises
`Vault__Static_Transport_Error` loudly (F5 preserved). `read()` tries the other layout before
surfacing an object error.

## A6 — tracked-wins fail-open → PINNED

Added the assertion the review asked for: `test_A6__head_unreadable_makes_scan_fail_loud`
corrupts the store and asserts that while `Vault__Head_Paths.paths` fails open (empty set),
the scan path (`status`) fails **loud** — so the two fail together and the deletion hazard
does not materialise. A comment on `Vault__Head_Paths.paths` records the coupling and warns
against making the scan tolerant of a corrupt head without gating tracked-wins.

## Agreements

I concur with every judgement call the review checked (tracked-wins in the engine, serve in
`core/serve`, no `Schema__OpenAPI_Document`, cover `updated` from the head commit, I6
excluding `local/config.json`, the mirror's three-way verdict) and with the "still owed" list
(P8, cells 5/6/8/10/12, the workflow generator, read-write attach branch registration, the
integration suite, decision 16). Nothing in the review needed pushback.

**Change control:** pack `CHANGELOG.md` r16; repo `CHANGELOG.md` `[Unreleased]` updated.
