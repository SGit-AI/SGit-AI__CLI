# 12 — Accepted risks (decision 16 and the AppSec §9 register)

**Date:** 2026-08-20 · **Status:** DECIDED by the maintainer · **Source:** AppSec review
`team/explorer/appsec/reviews/08/19/v0__appsec-review__static-publishing.md` (SP-1…SP-15)

This file records what we are **deliberately not defending against** in v1, the exploit
paths that follow, and the conditions under which each acceptance stops being reasonable.
It exists so the acceptance is a decision with a rationale, not a silence.

---

## 1. First, a correction to the threat model

The decision was taken on the reasoning *"a MITM attacker to be effective would need the
vault key."* **That is not the case, and the acceptance should rest on the real shape of
the risk rather than on that premise.** Nowhere in these attacks is the **vault (write) key**
required. The vault key defends the *server's* named-branch write path; a static host has
no server-side authorisation to defeat, so there is nothing for it to stop.

| Attack | Key needed | Why |
|---|---|---|
| **Rollback / freeze** — serve a coherent older snapshot | **none** | pure replay of bytes the publisher genuinely produced. Every AES-GCM tag, every content-address, every decrypt succeeds — they are *authentic bytes from the wrong point in time* |
| **Whole-site substitution, PUBLIC vault** | **none** | the read key is published in the folder by design. An attacker creates their own vault, publishes it `--visibility public`, and serves it at a URL the reader trusts. The loader finds *that* folder's key file and decrypts happily |
| **Whole-site substitution, PRIVATE-read vault** | the **read** key | to produce ciphertext that decrypts under the reader's key. Note this is strictly *more* than reading: it lets a read-key holder show a reader content the publisher never wrote |
| **Modifying one object in place** | none, but **detected** | `sha256(ciphertext)==id` catches it once SP-1 lands (P1). This is why SP-1 is a must-fix |

So the accurate statement of what is accepted: **a party who can control what bytes appear
at the URL can control which *version* a reader sees, and — for public vaults — which
*vault* they see, without holding any secret.**

## 2. What still holds, unconditionally

Accepting the above does not weaken these, and they are the properties the product actually
claims:

- **Confidentiality.** The host cannot read content. No attack here decrypts anything.
- **Per-object integrity under the reader's key.** AES-GCM authenticates every object;
  after SP-1, content-addressed objects are additionally id-verified before being written.
- **No key reaches a server** (I2). Unchanged.
- **A private vault's content is not forgeable by the host** — forging *that* needs the read
  key, which the host does not have at `bare`/`named` visibility.

## 3. The risk rating, per tier — and why "not High" is right for one of them

The AppSec review rated SP-2 **High**. That rating is correct *for the tiers it was written
against*; it is not correct for all of them, and the pack now separates them:

| Tier | Rating | Rationale |
|---|---|---|
| **Public vault** (key published, content is meant to be world-readable) | **Low — ACCEPTED** | a stale public handbook is a correctness annoyance, not a breach. Substitution is bounded by URL/host trust, which is the same trust every website on the internet runs on. No confidentiality loss is possible |
| **Private-read** (read key held by a named audience) | **Medium-High — NOT accepted** | gated by decision 16. A reader who is shown last month's version of a document they are relying on has been meaningfully attacked, and they have no signal |
| **CI / automated consumers** | **Medium-High — NOT accepted** | a pipeline that acts on vault content and cannot detect a rollback will re-run last week's decision. Machines have no "this looks old" intuition |

**The rating is content-dependent, and this is the line worth watching.** For a handbook,
low. For a vault whose content *drives a decision* — dependency manifests, policy documents,
agent instructions, allow-lists, anything a machine or a person acts on — a rollback attack
is the whole attack, and the rating rises regardless of tier. **If sgit vaults start being
used that way in public deployments, decision 16 should be revisited before the use spreads,
not after.**

## 4. Mitigations available today, without decision 16

None of these are a substitute for a signed head; all are free and worth stating in the docs:

- **HTTPS only.** It does not stop a malicious host, but it removes the network MITM from
  the picture entirely. The `http://` warning added to P1 (SP-6) is the CLI half.
- **Cross-check against the live API.** A reader who also has SG/API access can compare the
  static head against the authoritative named branch — the server *does* have the real head.
  This is the strongest check available today and costs one request.
- **Publish the head out of band.** A commit id in a release note, README, or chat message
  lets any reader confirm what they should be seeing. Cheap and human-checkable.
- **A future `--expect-head <commit-id>` flag** on clone/pull would turn that into a machine
  check (REASONED — not specified in any phase yet; a candidate if decision 16 is deferred
  further).

## 5. The rest of the register (AppSec §9), decided

| # | Accepted risk | Condition on the acceptance |
|---|---|---|
| 1 | **Static hosting has no revocation.** Rotation = re-key = a new vault; published bytes on a git host stay in history | UX must say "bare = unlisted, **not** access-controlled" (landed, `02` §1) |
| 2 | **First-view forgery bounded by URL/host trust** (SP-14) | docs must not imply authenticity the design does not provide (landed, `01` §1) |
| 3 | **Public-vault freshness** (SP-2, public tier only) | §3 above — revisit if public vaults start carrying decision-bearing content |
| 4 | **`--api-docs=cdn` puts jsdelivr on the reader path** | SRI + exact pin + `no-referrer` + mandatory CSP (landed, `08` §4). Residual: availability, reader-IP-to-CDN |
| 5 | **`manifest.json` discloses estate shape at `bare`** | required for keyless custody (I3); one-line notice in publish output (landed, `02` §1) |
| 6 | **CI config travels with the vault** | **superseded by decision 17** — `.github/` becomes ignored, so this risk mostly evaporates (§6) |

## 6. Decision 17 — `.github/` is ignored by default, with one required safeguard

**Decided:** add `.github` to `ALWAYS_IGNORED_DIRS`. The rationale is sound and stronger than
the SP-4 mitigation it replaces: workflow files inside a vault buy almost nothing, and they
are the exact payload that turns *vault-write* into *code execution on the publisher's
runner* — which, for a private vault, reaches `SGIT_READ_KEY`. Removing them from the vault
removes the escalation at its source rather than mitigating it downstream.

**But it cannot ship as a bare list addition**, because of the constraint attached to the
decision (*"as long as there is no side effects on existing vaults"*). Verified in code:

- `Vault__Ignore` has **no git-style "already-tracked files are exempt" rule**. The
  `'tracked'` reason code (`Vault__Ignore.py:155`) means only *"matched no ignore rule"* — it
  is not a tracked-file exemption.
- The work-tree scan prunes ignored directories outright. *(r15 correction, found by
  implementation: the load-bearing prune is `Vault__Sync__Base._scan_local_directory` —
  used by status, commit and pull — with the same prune repeated in branch-switch, stash,
  revert, merge, diff and bare walks. The originally-cited `Vault__Sync__Push.py:771-773`
  is only the pre-push `.conflict`-file scan; push itself never walks the work tree for
  content, so the deletions are recorded by `sgit commit`, then propagated by push.)*

So on upgrade, a vault that currently tracks `.github/**` would see those files **disappear
from the next push's tree** — recorded as deletions — and a later pull/checkout elsewhere
could remove them from that work tree via `_remove_deleted_flat`. That is silent content
loss caused by a version bump: precisely the failure this project rejected when it declined
to add `.site` to the same list (`CHANGELOG` r8).

**Required implementation shape (P0, before or alongside P1):**

1. **Tracked-wins.** A newly-added ignore rule must not remove content already present in
   the vault head. Match git: ignore rules govern *untracked* files only. Either implement
   the exemption in `Vault__Ignore` (needs the current tree, so it belongs at the call site)
   or scope the rule to files not present in the head tree.
2. **Migration notice.** On the first run against a vault whose head tracks `.github/**`,
   say so plainly and name the choice: keep tracking (grandfathered) or
   `sgit vault ignore --apply .github` to remove them deliberately, in one visible commit.
3. **Assert it.** A test that fixes a vault tracking `.github/workflows/x.yml`, upgrades the
   ignore set, pushes, and asserts the file is **still in the head** — plus the converse for
   a fresh vault, where `.github/` is never added.

Only requirement 1 is load-bearing for the maintainer's constraint; 2 and 3 make it visible
and keep it true.

---

**Review cadence:** these acceptances are v1 scope. Decision 16 returns to the table when
private-read or CI tiers are promoted from tabletop to supported, and — per §3 — if public
vaults begin carrying content that machines or people act on directly.
