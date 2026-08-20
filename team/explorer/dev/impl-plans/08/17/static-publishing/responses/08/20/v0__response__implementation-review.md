# Response to the implementation review (A1–A6)

**Responding to:** `team/explorer/architect/reviews/08/20/v0__review__static-publishing-implementation.md`
**Branch:** `claude/sgit-cli-review-rxll54`
**Date:** 2026-08-20 · **Suites after fixes:** 3812 unit / 122+20 qa, green
**Update:** A1 is now **closed at the root** (your option 3), not merely visible — see §A1.

The review is accurate. I reproduced both High findings independently before touching code —
the object swap on a never-moved vault (A1) and the `.git/hooks/pre-commit` write into the
victim's directory (A2) — and all six findings are now addressed. Verdicts below.

## A1 — SP-1 bypassable on every vault → **CLOSED** (your option 3)

Confirmed and important: you were right that the fallback is unconditional, not move-scoped.
My debrief §6 under-scoped it. First shipped option 1 (make it visible); the maintainer then
chose **option 3**, so the hole is now closed at the root rather than narrated.

**What changed.** `sgit vault move` no longer re-encrypts objects in place under their old
ids. `Step__Move__Build_Temp_Vault` performs a bottom-up topological graph rewrite: object
types come from **reachability** (refs → commits → trees → entries) rather than plaintext
sniffing — a blob that happens to be JSON with a `schema` key would otherwise be misparsed as
a tree — and objects are rewritten blobs → trees (children first) → commits (parents first),
each stored at its **recomputed** id with every reference remapped (merge commits' second
parents included). Refs are repointed at the rewritten head.

**Therefore the fallback is deleted.** `Vault__Verified_Write` is strict for keyed and
keyless callers alike; the `AUTHENTICATED` verdict is gone. Verified end-to-end: the swap you
reproduced is now **refused**, the substituted content never reaches the working copy, and a
moved vault has **zero** objects failing their content address and clones cleanly. The QA I7
swap cell asserts the refusal.

**Two bonuses worth flagging.** (1) It also closes a latent **linkability** leak: because
move kept ids, a vault and its moved copy shared every `obj-cas-imm-*` id — a trivial
correlation for anyone seeing both stores, which undercut move's "new, unlinkable identity"
purpose. (2) `store_at`'s CAS-breaking mode now has no caller in move, so "the content address
is never broken" is true system-wide again — the property that made SP-1 clean to begin with.

**A tested expectation was deliberately reversed, and you should sanity-check that call.**
`test_Vault__Sync__Move__Object_IDs.py` and `Vault__Sync__Move.test_object_ids_are_stable_after_move`
asserted that pre-move ids must survive — exactly the behaviour that caused A1. I rewrote them
to assert the intent they were protecting (no *content* lost: work tree identical, object
count preserved, one sentinel per named branch) plus the new invariant (every object verifies
against its own id; no id reused). The two sentinel tests that compared against pre-move ids
now assert chaining and tree-reuse structurally *inside* the moved vault.

**Still open — the maintainer's call:** migration for vaults already moved by an older sgit.
Their objects keep the old un-addressed ids, so a strict reader refuses them. The clone
diagnostic names the remedy ("if EVERY object failed … re-run `sgit vault move` to normalise
the store"), but that is a manual step; if such vaults exist in the wild, a detect-and-normalise
path may be worth adding before release.

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
