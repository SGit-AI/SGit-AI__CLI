# Response to the follow-up review (B1–B3)

**Responding to:** `team/explorer/architect/reviews/08/20/v1__review__fixes-for-A1-A6.md`
**Branch:** `claude/sgit-cli-review-rxll54`
**Date:** 2026-08-21

Thank you for auditing the move rewrite directly and for endorsing the test reversal — that
was the call I most wanted a second pair of eyes on. All three new items are addressed
below, and B2's migration question — the one you asked not to release without — has since
been **decided by the maintainer: ship as-is, strict** (§B2). Nothing from v0 or v1 is
open.

## B1 — refused tree/commit crashed the clone → FIXED (all three delivery points)

Confirmed exactly as described: the per-object fail-soft covered blobs (and commit
*lineage*), but a refused tree — or the head commit at checkout — was later **required**,
and `Vault__Object_Store.load`'s raw `FileNotFoundError` escaped `runner.run` with an
internal store path, before the r17 diagnostic could fire. Your three suggestions are
implemented as suggested:

1. **Typed error, naming object and remedy.** `Vault__Object_Store.load` now raises
   `Vault__Object_Missing_Error` — a `FileNotFoundError` *subclass*, so every existing
   absent-object handler (sparse clones, cache rebuilds, commit-lineage skips) keeps
   working — whose message names the object, never a path. The clone entry points funnel
   through one `_run_clone_workflow`, which translates a missing object into
   `Vault__Integrity_Error` **when the missing id is one the content-address check
   refused**: the message names the object, the refusal count, and both remedies (legacy
   move → normalise; otherwise → hostile host). A miss that is *not* explained by a
   refusal still surfaces as a missing-object error — an absent object is not an
   integrity claim.
2. **Summary on failure paths.** The refusal summary moved into a `finally`, so it is
   emitted whether the run completes or dies — including in the exact case it was written
   for (every object refused → tree required → run dies).
3. **stderr fallback.** With `on_progress=None` the summary prints to stderr. A library
   caller is never silent on a security refusal.

The CLI also renders `Vault__Integrity_Error` on its own branch — without the generic
missing-file "vault may be corrupted, try fsck" hint, which would have been exactly the
F5-shaped misdiagnosis you flagged.

Tests: a tampered **tree** on a hostile host now asserts the typed error (object named,
remedy named, no raw path text), the summary emission on the failed run, and the stderr
fallback (`test_refused_tree_raises_typed_integrity_error`,
`test_refusal_summary_reaches_stderr_without_callback`). The existing tampered-blob test
still passes unchanged — blob refusal remains fail-soft.

## B2 — legacy-moved vaults → publish-side detection ADDED; migration DECIDED (ship as-is)

You are right that "there is a diagnostic" was not true in the crash case — with B1 fixed
it now is. Beyond that, the half of B2 that has a clearly correct owner-side answer is
implemented:

- **`sgit publish` now refuses an unverifiable store.** Manifest enumeration already
  computes every object's full sha256, so the check is free: any `obj-cas-imm-*` whose
  bytes do not hash to its id fails the publish with `Vault__Integrity_Error`, naming the
  first offending object and the remedy (`sgit vault move`, then publish again). The
  publisher is exactly the party who holds the vault key and a good copy — the one actor
  your review notes *can* act on the advice. A publisher can no longer unknowingly ship a
  vault that every current-version reader refuses. (`sgit vault serve`'s auto-publish
  inherits the refusal, so serving a legacy store is loud too.)

- **The migration question is now decided: ship as-is, strict.** The maintainer's call,
  taken on the three options as your review framed them. No detect-and-normalise pass and
  no read-side allowance flag: strict refusal stays the behaviour everywhere, and the
  three diagnostics added in r17/r18 carry the load — clone names the object and the
  remedy, publish refuses the store before it ships, and `sgit vault move` warns that
  published surfaces go stale. A key-holder normalises by re-running `sgit vault move`.

  The reasoning, recorded so a later reader does not have to reconstruct it: the
  population at risk is vaults moved by a pre-release sgit, which is small-to-empty; a
  read-side allowance re-opens a slice of A1 by construction (a flag an attacker's
  instructions can tell a user to pass is not much of a gate); and a normalise pass is
  code written for a migration that may have no subjects. If such vaults do turn up, the
  move rewrite is already the normalise pass — wiring `sgit check fsck` to detect and
  offer it is a contained follow-up, not a release blocker. **This is the release
  decision the review asked for; nothing from v0 or v1 is now open.**

## B3 — merge fixture merged nothing → FIXED

Confirmed; the assertion claimed coverage it had not earned. The fixture now merges
`side` into `main` through the production merge-commit path (a merge state +
`Vault__Sync__Commit`, the same code pull uses), and the test enforces both ends: the
fixture must contain a real two-parent commit (`assert merge['merge_commit']`, plus a
decrypt-and-count guard so it cannot silently regress), and after the move the merge
commit must survive with **both** remapped parents present in the store. The
divergent-branch shape is kept, so multiple-roots coverage is not lost.

## The documentation note → DONE

`sgit vault move` now ends its output warning that every previously published surface
(manifest, bundles, deep links) is stale and naming `sgit publish` as the follow-up; the
repo CHANGELOG's move entry says the same. Agreed this is the linkability fix seen from
the publisher's side — a silently-404ing Pages site would have been diagnosed as anything
but the move.

## Change control

Pack `CHANGELOG.md` r18 (B1/B3 + publish-side detection) and r19 (the B2 release
decision); repo `CHANGELOG.md` `[Unreleased]` updated (integrity-refusal diagnosis entry
added; move entry extended with the republish note).

**Suites:** 3815 unit passed · 122 passed / 20 skipped qa.
