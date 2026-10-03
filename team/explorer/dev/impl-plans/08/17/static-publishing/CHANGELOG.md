# Change control — static-publishing pack

Newest first. **Every commit that edits a spec file in this pack adds an entry here** —
what changed, *why* (the trigger), and which decisions moved. A reader returning after a
gap reads this file first; a developer agent's definition of done includes updating it
(`00` §4). The pack has reversed load-bearing decisions more than once — that is healthy,
but only if the reversals are legible in one place.

Conventions: **decisions** reference the numbered table in `06` §1; **R-numbers** are
findings from the 19 Aug review (`team/explorer/architect/reviews/08/19/v1__…`); **F-numbers**
are live findings from the executed tabletops (`10`/`11`); **SP-numbers** are from the AppSec
review (`team/explorer/appsec/reviews/08/19/v0__appsec-review__static-publishing.md`).

---

## 2026-08-24 — r20: new spec `13` — derived publish vaults (`sgit vault derive`)

**Trigger:** maintainer — *"the creation of a rekeyed vault … publish what in essence is a
copy of a vault, without actually exposing the read-only key or the vault key of the vault
to publish"*, in two modes (nuke history / keep all history), with the derived key stored in
the source's `local/` folder and **incremental** refresh on new commits.

New file [`13__derived-publish-vaults.md`](13__derived-publish-vaults.md). Status: BUILD
SPEC, awaiting sign-off on **decisions 18–21**. Nothing implemented yet.

**Why it exists.** `publish --visibility public` writes the *source* vault's read key, which
decrypts that store for ever — including other branches and everything published later — and
the published store shares every object id with the source, so the two can be correlated. A
derived vault has its own key, id and object ids; publishing it exposes only itself.

**No new crypto — both modes are engines that already exist.** Snapshot mode is a
flatten-and-build of the head tree (not `rekey()`, which is in-place and needs a work tree);
history mode is the r17 move graph rewrite. The new work is the non-destructive wrapper and
the incremental state.

**Findings recorded while specifying it** (each changes the design, none was obvious):

- **The move sentinel would leak the source vault id.**
  `Step__Move__Write_Sentinel_Commits` writes `from-vault-id: <old>` into a commit message.
  Publishing hands out the read key, so every reader would decrypt it. The derive path omits
  the sentinel step, with a test asserting no derived commit names the source vault.
- **Refresh needs a persisted id-map or the whole store re-addresses every time.** The r17
  `emit()` uses `crypto.encrypt`, i.e. a random IV, so identical plaintext re-encrypts to a
  different ciphertext and therefore a different content address. Without the map, one
  changed file would invalidate the entire manifest, every bundle and every deep link.
- **Snapshot refresh must prune, or deletion is cosmetic.** An unreachable blob stays on
  disk, stays in `manifest.json`, and stays decryptable under the published key — so a
  publisher who deletes a file and refreshes would wrongly believe it was withdrawn.
- **The id-map is a correlation oracle** (source id → derived id) and is secret-grade:
  local-only, never pushed, never in the published surface. New invariant I12.
- **Containment:** the derived folder must live outside the source work tree, or the derived
  store becomes source vault content on the next commit — the `07` §3 amplification loop.

Adds invariants **I8–I12** and test cells **15–23**; phases **PD1–PD4**.

**Open, to verify during implementation (not asserted in the spec):** whether `bare/keys`
per-branch signing public keys survive the rewrite verbatim and thereby give an observer a
join key between source and derived stores.

## 2026-08-21 — r19: the legacy-moved-vault migration DECIDED — ship as-is, strict

**Trigger:** maintainer, on the B2 release decision the follow-up review asked for.

**Decision: ship as-is.** No detect-and-normalise pass, no read-side allowance flag.
Strict content-address verification stays the behaviour on every read path, and the
diagnostics added in r17/r18 carry the migration load:

- **clone** — names the refused object and the remedy (`Vault__Integrity_Error`), reaching
  stderr even with no progress callback and even when the run fails;
- **publish** — refuses a store whose objects do not hash to their ids before anything
  ships, so a publisher cannot unknowingly serve a vault every reader will refuse;
- **move** — warns that previously published surfaces go stale and to republish.

A key-holder normalises a legacy store by re-running `sgit vault move`.

**Rationale, recorded so it need not be reconstructed:** the affected population is vaults
moved by a pre-release sgit — small to empty. A read-side allowance would re-open a slice
of A1 by construction (a flag a hostile host's instructions can talk a user into passing is
a weak gate). A normalise pass is code written for a migration that may have no subjects —
and if such vaults do appear, the move rewrite *is* the normalise pass, so wiring
`sgit check fsck` to detect and offer it is a contained follow-up rather than a release
blocker.

**Status: every finding from the v0 and v1 architecture reviews (A1–A6, B1–B3) is closed
or decided.** The static-publishing feature set has no open review items.

## 2026-08-21 — r18: B1/B3 from the follow-up review fixed; publish refuses an unverifiable store

**Trigger:** architect follow-up review
(`team/explorer/architect/reviews/08/20/v1__review__fixes-for-A1-A6.md`) — all six
A-findings verified closed; three new items raised (B1 blocking, B2 a maintainer decision,
B3 a test gap). Suites after fixes: 3815 unit / 122+20 qa, green.

- **B1 fixed — a refused tree/commit now diagnoses as a refusal, not a stray file error.**
  The per-object fail-soft covered blobs; a refused tree or commit was later *required* by
  the walk/checkout and crashed the clone with a raw `FileNotFoundError` naming an internal
  store path — and since the crash happened inside `runner.run`, the refusal summary (added
  in r17 for exactly this case) never fired. Three-part fix, per the review's suggestion:
  `Vault__Object_Store.load` raises a typed `Vault__Object_Missing_Error` (a
  `FileNotFoundError` subclass, so every existing absent-object handler keeps working)
  naming the object, clone translates it into `Vault__Integrity_Error` naming the object
  and the remedy whenever the missing id is one the content-address check refused, the
  refusal summary is emitted in a `finally` (failure paths included), and it falls back to
  stderr when no progress callback is passed (library callers are never silent on a
  security refusal). The CLI renders the integrity error without the misleading
  corrupt-vault/fsck hint.
- **B2 partially addressed — publish-side detection added; the migration decision remains
  open.** `sgit publish` now refuses a store whose content-addressed objects do not hash
  to their ids (free: manifest enumeration already computes every sha256), naming the
  remedy — so a publisher can no longer unknowingly ship a legacy-moved vault that every
  current-version reader refuses. The remaining call — write-side detect-and-normalise vs
  an explicit read-side allowance for *already-published* legacy vaults — is the
  maintainer's, flagged for decision before release.
- **B3 fixed — the merge fixture now contains a real merge.** The two-parent remap's
  stated coverage merged nothing; the fixture now creates a genuine two-parent merge
  commit through the production path (merge state + `Vault__Sync__Commit`), asserts the
  fixture contains one, and asserts post-move that the merge commit survives with both
  remapped parents present in the store.
- **Doc note (review's "one documentation note"):** `sgit vault move` output now warns
  that every previously published surface (manifest, bundles, deep links) is stale after a
  move and names `sgit publish` as the follow-up; repo CHANGELOG updated to match.

## 2026-08-20 — r17: A1 CLOSED — `sgit vault move` rewrites object ids; the key-fallback is gone

**Trigger:** maintainer, after the option analysis — *"I agree can you implement option 3"*.
A1 was left visible-but-open in r16; it is now closed at the root. Suites: 3812 unit /
122+20 qa, green.

**The root cause.** An object id IS `sha256(ciphertext)[:12]` — that is what lets any reader
verify an object with no key and no trust in the host. `sgit vault move` re-encrypted every
object under the new key while KEEPING the old id (`store_at`, "deliberately breaks the CAS
invariant"), so in a moved vault **no** object hashed to its own id. That forced the reader
to relax the check, and a relaxed check is what let a hostile host swap two *authentic*
objects undetectably. The weakness was never really about moved vaults: the exemption
applied to every clone that held a key.

**The fix (option 3).** `Step__Move__Build_Temp_Vault` now performs a bottom-up topological
graph rewrite instead of an in-place re-encrypt:

- Object TYPES come from **reachability** (refs → commits → trees → entries), never from
  sniffing the plaintext — a blob whose content happens to be JSON with a `schema` key would
  otherwise be misparsed as a tree and have its "entries" rewritten.
- Rewrite order: blobs → trees (children first) → commits (parents first), each object
  re-encrypted under the new key and stored at its **recomputed** id, with every reference
  remapped through an `{old_id: new_id}` map. Merge commits' second parents are remapped too.
- Refs are repointed at the rewritten head commit; an undecryptable object is carried
  verbatim at its existing id (which is still its true content address, so the invariant
  holds even there); unreachable orphans are carried with new ids and stay unreachable.
- Post-order traversal is iterative — a commit chain can be long.

**Consequences.**
- **A1 is closed.** `Vault__Verified_Write` is now strict for keyed and keyless callers
  alike: the AUTHENTICATED verdict and the "but it decrypts under my key" fallback are
  **deleted**. The swap attack is refused and the substituted content never reaches the
  working copy (verified end-to-end; the QA I7 swap cell asserts it).
- **A latent linkability leak is closed too.** Because move kept ids, a vault and its moved
  copy shared every `obj-cas-imm-*` id — a trivial correlation for anyone who saw both
  stores, which undercut move's whole "new, unlinkable identity" purpose. No id survives a
  move now.
- **`store_at`'s CAS-breaking mode has no remaining caller in move**, so "the content
  address is never broken" is true again system-wide — which is what made SP-1 clean in the
  first place.
- **A tested expectation was deliberately reversed.** `test_Vault__Sync__Move__Object_IDs.py`
  and `Vault__Sync__Move.test_object_ids_are_stable_after_move` asserted that pre-move ids
  must survive — precisely the behaviour that caused A1. They now assert the intent those
  tests were protecting (no *content* is lost: work tree identical, object count preserved,
  one sentinel per named branch) plus the new invariant (every object verifies against its
  own id; no id is reused). The two sentinel tests that compared against pre-move ids now
  assert the same properties structurally inside the moved vault.

**Open, and the maintainer's call: migration for vaults already moved by an older sgit.**
Their objects keep the old un-addressed ids, so a strict reader refuses them. The clone
diagnostic names the remedy ("if EVERY object failed … re-run `sgit vault move` to normalise
the store"), which works but is a manual step. If such vaults exist in the wild, a
detect-and-normalise path may be worth adding before release.

## 2026-08-20 — r16: architecture review findings addressed (A1–A6)

**Trigger:** the architecture session reviewed the implementation
(`…/architect/reviews/08/20/v0__review__static-publishing-implementation.md`) and raised two
High integrity findings plus four smaller ones. All reproduced independently, all fixed on
`claude/sgit-cli-review-rxll54`. Suites: 3811 unit / 121+20 qa, green.

- **A1 (High) — SP-1 key-fallback was silent on EVERY vault, not just moved ones.** The
  content-address fallback ("accept if it decrypts under the read key") fires on any clone
  with a key, so two authentic objects swapped between their ids were both written with no
  warning — a substitution the reader could not see. Fixed by making it VISIBLE:
  `Vault__Verified_Write` now returns a verdict (`verified` / `authenticated` / `refused`);
  clone and pull/fetch count `authenticated` objects and print a once-per-run warning naming
  the substitution risk. The QA I7 cell gained the swap case (the old cell used garbage bytes
  that never engaged the fallback). The deeper closure (gate the fallback on a move marker,
  or have move rewrite ids — decision-16 adjacent) remains a maintainer decision, now with
  the hole no longer silent.
- **A2 (High) — structural directories were not exempt from tracked-wins.** git *refuses*
  `.git`, it does not merely ignore it; the same must hold for `.sg_vault`. A crafted vault
  head could carry `.git/hooks/pre-commit` (code execution on the victim's next git command)
  or `.sg_vault/local/…`, and clone wrote them into the victim's directory — with tracked-wins
  keeping them tracked. Fixed with a storage-layer protected set
  (`Vault__Path_Guard.VAULT_PROTECTED_DIRS` — `.sg_vault`, `.sg_vault_new`, `.sg_vault_old_*`,
  `.git`): the ignore engine refuses these even when a head tracks them (`.github` grandfathering
  is untouched — it is a preference, not structural), and `Vault__Sub_Tree.checkout` /
  `_checkout_flat_map` skip writing any entry under a protected segment.
- **A3 (Medium) — `--bind` disabled the DNS-rebinding defence.** The Host check now stays on
  when widened: loopback names and IP-literal Hosts are allowed (rebinding requires a domain
  name), domain-name Hosts are refused — so the operator's browser is defended on 0.0.0.0 too.
- **A4 (Low) — local static reads are path-guarded** (inline, since the network layer may not
  import storage): a manifest `file_id` with `../` resolves to absent rather than reading
  outside the served folder.
- **A5 (Low) — non-404 HTTP status is now a typed `Vault__Static_Object_Error`** and fails
  soft per object in `batch_read` (recorded, run continues) instead of a bare `RuntimeError`
  aborting the run; a dead host still raises `Vault__Static_Transport_Error` loudly (F5).
- **A6 (Note) — the tracked-wins fail-open is pinned.** `Vault__Head_Paths.paths` returns an
  empty set on error (disabling tracked-wins); a comment and
  `test_A6__head_unreadable_makes_scan_fail_loud` document and pin that this is safe only
  because the scan path fails loud on the same corruption — the two fail together.

Judgement calls the review checked and agreed with (tracked-wins in the engine, serve in
core, no OpenAPI schema class, cover `updated` from the head commit, I6 excluding
`local/config.json`, the mirror's three-way verdict) are recorded there and unchanged.

## 2026-08-20 — r15: the pack implemented — P0–P7 and P9 landed; defects found by execution

**Trigger:** maintainer — *"please do the full implementation unless you hit a road block
or need an answer from me."* All v1 phases (P0, P1, P2, P3, P4, P4b, P5, P6, P7, P9) are
shipped code on `claude/sgit-cli-review-rxll54`; P8 stays deferred per decision 11.
Suites: 3796 unit / 121+20 qa, green. Spec files corrected where execution proved the
text wrong — per the pack's own rule that such text is a bug to report:

- **P0 call site was wrong** (`05`, `06`, `12` corrected): `Vault__Sync__Push.py:771-773`
  is the pre-push `.conflict` scan; push never walks the work tree for content. The
  deletion-producing walk is `Vault__Sync__Base._scan_local_directory` (status/commit/pull)
  with the same prune repeated across ~8 walk sites (branch-switch, stash, revert, merge ×2,
  diff, bare) — so tracked-wins landed **inside `Vault__Ignore`** (fed by the new
  `Vault__Head_Paths`), not at one call site. The escape hatch the migration notice names
  (`sgit vault ignore --apply`) did not exist as a command; it does now
  (`Vault__Ignore__Apply` — one visible commit, work tree untouched).
- **SP-1's "verify unconditionally" is unbuildable against shipped move semantics**
  (raise, not resolved silently): `sgit vault move` re-encrypts every object in place
  KEEPING its old id (`store_at` deliberately breaks the CAS invariant), so in a moved
  vault no object hashes to its id — unconditional verification refuses the whole store
  (caught by the move test suite; shipped `fsck` has the same latent conflict). Implemented
  rule: sha256 first; on mismatch accept only if the object still AES-GCM-authenticates
  under the reader's key (unforgeable without the key); keyless consumers (mirror) get the
  strict check and report such objects as host-attested, never verified. **Residual gap
  needing an architecture decision:** on any transport, an attacker who can serve bytes can
  swap one VALID ciphertext under another object's name and the GCM fallback accepts it —
  inherent to move's id reuse; candidate fixes are move rewriting ids or a signed manifest
  binding names (decision-16 adjacent).
- **I6 vs decision 5** (test nuance, `04`-adjacent): publish must record the clone's
  visibility choice in `.sg_vault/local/config.json`, so "the only path that changed is
  `.sg_vault/publish/`" holds for everything except that one never-pushed local-state file;
  the I6 assertions exclude it explicitly.
- **`02` §6 stale row** replaced: the "plaintext warning on a vault-supplied index.html"
  was pre-r5 residue (publish emits no vault content); the load-bearing string is P8's
  expand-time note.
- **`07` §6**: the three expansion checkboxes marked P8-deferred; noted that "manifest
  records which file is at the root" can only be an expansion-time act.
- **`00` §4**: the qa invocation corrected (`pytest tests/qa -q`; the `-m qa` filter
  selects only a subset) and counts refreshed.
- **`05` P3**: server moved to `core/serve/` — the layer rules forbid network → storage
  and `Vault__Path_Guard` lives in storage.
- **Deliberate deviation:** no `Schema__OpenAPI_Document` Type_Safe class (P4b) — OpenAPI
  is an externally-specified nested-map format; the document is generated directly from the
  manifest enumeration. Raised rather than silently modelled.
- Lab scripts retired by their shipped replacements (`simulate_publish.py` → `sgit publish`,
  `attach_simulated.py` → `sgit vault attach`, `ci_publish_readkey.py` → read-only-clone
  publish, now a tested path); `reader_clone.py` ports to the shipped transport.
- Decision 13's canonical repo-side gitignore set ships as
  `Vault__Repo_Ignore.CANONICAL_REPO_GITIGNORE`, asserted literally in the QA suite;
  `sgit vault backup` warns in a git work tree missing the `backups/` line.

## 2026-08-20 — r14: the register decided — decisions 16 and 17, and a new P0

**Trigger:** maintainer, on the AppSec §9 accepted-risk register — *"for decision 16 I agree
with option (a)… but document this (the current situation and the security exploit paths and
risk that we are going to accept, and this is not a High risk)"*; *"on committing `.github`
folders to a vault I actually think we should add that as a default (and documented) vault
ignored folder"*; *"on the other decisions and issues to fix, as long as there is no side
effects on existing vaults and sgit functionality, then I'm good for them."*

**All seventeen decisions are now signed off.** New file `12__accepted-risks.md` carries the
register; `06` §1 records both decisions; `05`/`00` gain **P0**.

- **Decision 16 — DEFERRED for the public tier, accepted and documented; still required
  before private-read or CI are supported.** One correction to the premise it was decided on:
  *the vault key is not needed for any attack in this class.* Verified and tabulated in `12`
  §1 — rollback/freeze needs **no key** (replay of authentic bytes from the wrong point in
  time), whole-site substitution of a **public** vault needs **no key** (the read key is
  published by design), and substitution of a **private-read** vault needs the **read** key.
  The vault key defends the server's named-branch write path; a static host has no
  server-side authorisation to defeat. The acceptance still stands for public vaults, but on
  *harm* grounds rather than attacker-cost: `12` §3 rates public **Low — ACCEPTED**,
  private-read and CI **Medium-High — NOT accepted**. Named revisit trigger: any public vault
  whose content drives a decision (dependency manifests, policy, agent instructions,
  allow-lists) — rollback is the whole attack there, and the rating rises regardless of tier.
- **Decision 17 — `.github/` is ignored by default, and it ships with a tracked-wins
  exemption.** The rationale is stronger than the SP-4 mitigation it replaces: workflow files
  in a vault are the exact payload that turns *vault-write* into *code execution on the
  publisher's runner*, which for a private vault reaches `SGIT_READ_KEY`. But a bare
  `ALWAYS_IGNORED_DIRS` addition would break the maintainer's own condition. Verified in
  code: `Vault__Ignore` has **no** git-style tracked-file exemption (the `'tracked'` reason at
  `Vault__Ignore.py:155` means only "matched no ignore rule"), and the push walk prunes
  ignored directories outright (`Vault__Sync__Push.py:771-773`) — so on upgrade, a vault
  tracking `.github/**` would record those files as **deletions**, and a later pull elsewhere
  could remove them from that work tree. That is the same data-loss shape the pack rejected
  in r8 when it declined to add `.site`.
- **New phase P0** (`05`, `00` §5) — tracked-wins in the ignore engine **first**, the
  `.github` entry **second**, plus a one-time migration notice and a regression test that a
  vault tracking `.github/workflows/x.yml` still has it in the head after the upgrade. Small,
  but ordering-critical, and it touches the ignore engine — so it lands before other phases
  start adding files to vaults.
- **SP-4's workflow half is closed** by decision 17; P9's acceptance now scopes SP-4 to the
  reader-HTML half plus runner hardening.
- Register items 1–5 (no revocation, first-view trust, public freshness, CDN on the reader
  path, manifest estate-shape) recorded as accepted **with their conditions**, each already
  landed in the UX or architecture text. Item 6 (CI config in the vault) is superseded by 17.

Decision count **17**; phases now **P0**–P9; invariants unchanged at 7.

## 2026-08-20 — r13: AppSec review folded in (SP-1…SP-15, decision 16)

**Trigger:** maintainer — *"fire up an AppSec agent and do a thorough security review before
we start implementation."* Verdict: proceed with P1/P3; two must-fixes fold into P2/P5; one
decision (freshness) gates the private/CI tiers. The public-vault case the tabletops
exercised is not blocked. Full review: `…/appsec/reviews/08/19/v0__…`.

The systemic gap named: **no read-time root of trust** — every integrity claim in a
published folder is self-attested by that same folder. What landed in the pack:

- **SP-1 (High, CODE — verified) → P1 must-fix, new invariant I7.** The shipped clone path
  writes fetched objects with **no `sha256(ciphertext)==id` check** (`Clone__Workspace.save_file`;
  `verify_integrity` exists but no clone step calls it — confirmed against code). Contradicts
  `00` §3 and the `03` §2 diagram. Id-verify before write, per object.
- **SP-3 (High) → P5 must-fix.** The manifest is "hint not authority" only for the CLI
  (which can parent-walk); the keyless mirror and browser loader cannot fall back, so a host
  rewriting object+hash together yields a mirror that "verifies" corrupt bytes. Rule: for
  `obj-cas-imm-*`, recompute the id and **ignore the manifest `sha256`**. `01` §4 updated.
- **SP-8 (Medium) → P3 + P5 must-fix.** Manifest `file_id` is attacker-controlled and used
  as a write/serve path; route it (and the serve virtual route) through the existing
  `Vault__Path_Guard`; bound counts/sizes; dedupe. `04` gains a hostile-host fixture.
- **SP-9 (Medium) → P3.** `serve` needs a `Host`-header check (DNS-rebinding) and a sharper
  `--bind 0.0.0.0` warning.
- **SP-2 / SP-14 (High/Medium) → new decision 16.** No freshness/authenticity anchor: a host
  or `http://` MITM serves a coherent rolled-back or forged site undetectably. Recommend a
  signed monotonic head (verify key in `cover.json`). Public tier may accept the documented
  non-guarantee — now stated in `01` §1; private/CI tiers need the signature.
- **SP-4 (Med-High) → P9/decision 15.** Vault-write escalates to CI code execution + reader
  HTML via the vault→repo path; the CI story is not "supported" until the runner is
  least-privilege and the escalation is documented. P9 acceptance + template hardened
  (SP-10: SHA-pinned actions, pinned sgit, `persist-credentials: false`).
- **SP-7/SP-12 → P4/`02`:** "bare = unlisted, NOT access-controlled"; the bare manifest's
  estate-shape disclosure is noted. **SP-5/SP-6/SP-11** flagged for the P4 loader / Web team
  (session-memory keys, fragment + `http://` hygiene, mandatory CSP).

- **SP-6 → P1 + `01` §7.** The CLI half (warn when a *private* read key is used over plain
  `http://`) is P1 acceptance; the loader half (strip the fragment via `replaceState`, never
  put it in a link/redirect) is stated in `01` §7 for the Web team. `sgit_public_read_` is
  exempt — already public.
- **SP-11 → P4b + `08` §4.** The docs-page CSP is promoted from "belt and braces" to
  **required**, because that page shares an origin with a loader that may hold a key;
  `connect-src 'self'` is the exfiltration backstop.

Accepted-risk candidates (need an explicit maintainer decision, not silence) are listed in
the review §9. I7 makes the invariant count 7; decision count 16.

## 2026-08-19 — r12: r11's findings propagated into the spec files

**Trigger:** maintainer — *"did you also update the other files like the architecture
one?"* r11 updated `05`/README/template/CHANGELOG but left `01`, `02`, `03`, `00`, `04`,
`07` carrying pre-tabletop-11 content. The pack's own lesson (r8) repeated: findings must
land in every file that states the affected behaviour, not just where they were found.

- `01`: transport contract now states F5 in the method table (**only 404 ⇒ absent;
  connection errors raise, naming the host**) and gains §6 "the pipeline seam" — the CI
  sequence with the runner's key posture; loader discovery renumbered to §7.
- `02`: new §4 — `sgit vault attach` command surface (P9, marked FUTURE), strings taken
  from the executed drill incl. the wrong-key "Nothing written" refusal (now a
  load-bearing string); trailing sections renumbered.
- `03`: flow 6 — the CI pipeline sequence diagram.
- `00`: grounding read 7 (tabletop 11 + template; F5 for P1 builders, F6 + the attach
  stand-in for P9 builders).
- `04`: dead-host fixture requirement for F5 ("the error must not say 'no named ref'").
- `07`: composing row links the committed workflow template.

## 2026-08-19 — r11: tabletop 11 executed (simulated hosting)

**Trigger:** maintainer — *"No need to create the repos, just simulate it and update the
dev pack."* Executed all ten steps of the brief with real CLI/crypto and simulated
GitHub/Actions/Pages; `11__tabletop__publishing-pipelines.md` is the transcript, and
`templates/github-pages.yml` is now a committed artifact.

- **Confirmed executed:** the keyed-backup leak (zip carries `VAULT-KEY`; `local/`-only
  ignore stages it, canonical set excludes it); the attach drill (wrong key refused with
  nothing written; read-only and read-write both open the vault); the workflow file swept
  into the vault as content and arriving in the reader's clone (F1-generalisation policy:
  ACCEPTED, demonstrated); the full public pipeline with a zero-secret runner; R3 key-file
  drop on a forgotten `--visibility`; the keyless staleness check catching a forgotten
  republish; rollback via `git revert` (the site follows the **repo** timeline, not the
  vault's); provider-identical clone-backs (I1).
- **New findings:** **F5** — a dead host is reported as "vault has no named ref"
  (connection errors must raise loudly; only 404 means absent → P1 acceptance). **F6** —
  attach must be mode-exclusive and `Schema__Clone_Mode`-exact; the shipped clone-mode
  guard enforces this correctly (→ P9 acceptance). **F7** — `git checkout -- refs/` after
  a successful push reverts the head and deploys a stale site (safe ordering now in the
  workflow template). **F2 refined:** the pre-flight rewrites the local ref to server
  bytes on a refused push only when bytes differ (repro sharpened for the fix).
- Template hardened: fork guard file-tests the key glob (unmatched globs are truthy
  literals); F2/F7 ordering comment. `simulate_publish.py` gains the read-only-clone path
  (publish from `clone_mode.json` — C7 through the attach route); `attach_simulated.py`
  added (P9's stand-in, named for retirement).
- **Still owed to a real-GitHub run:** Pages propagation timing, secret masking in logs,
  measured ACAO/cache-control/dot-dir rows for real providers.

## 2026-08-19 — r10: the publish folder is committable; the gitignore that matters guards keys

**Trigger:** maintainer — *"why are we `.gitignore *`-ing `.sg_vault/publish`? If that
folder is not on GitHub, how can the corresponding GH Action know what to do?"* — plus the
tabletop-11 brief from the nhi.sgit.ai session (landed as
`11__tabletop-brief__publishing-pipelines.md`), whose §5 edits stand on code inspection.

- **The publish folder's `*` self-ignore is removed.** In the canonical one-repo flow the
  folder must reach GitHub — it is what the Pages workflow deploys — and after r9 it is a
  few KB of generated plaintext with nothing sensitive (the key file is prompt-gated).
  Plain `git add -A` now includes it; the `git add -f` step dies. Mockup surface counts
  revert; the manifest example drops the `.gitignore` entry.
- **The canonical repo-side `.gitignore` is three lines, and it guards key material**
  (decision 13): `.sg_vault/local/` (live secrets), **`.sg_vault/backups/`** (backup zips
  contain `bare/` + local config and, with `--include-key`, **the vault key itself as
  `VAULT-KEY`** — verified in `Vault__Backup.py`), `.sg_vault_new/` (a second store incl.
  its own secrets during a move). Tabletop 10's `local/`-only ignore was insufficient;
  correction note added there. sgit should emit/maintain the set; `backup` in a git work
  tree without the `backups/` line warns (new load-bearing string in `02`).
- **The attach gap is executed evidence** (decision 14, **new phase P9**):
  `sgit clone-headless` refuses inside a vault and `sgit status` errors on the missing
  `local/vault_key` — no shipped command binds a key to a fresh git checkout of a one-repo
  vault. `sgit vault attach` specified with acceptance criteria; it retires the tabletop
  lab script.
- **Decision 15 opened:** the deploy workflow comes from a **CLI generator** (recommended)
  with the human-readable copy on sgit.ai — a docs-page copy cannot track publish
  semantics that changed nine times in three days.
- New rule in `00`: **key material never lands in git**; `04` gains the literal ignore-set
  assertion and the keyed-backup cell.

## 2026-08-19 — r9: publish no longer copies the ciphertext

**Trigger:** maintainer, reading `01` §3 after r8 — the
`api/vault/read/<vault_id>/bare/**` byte-copy inside the publish output was still wrong:
the served root should get **the store itself** (*"that root folder/location could only
contain the `.sg_vault/bare/*` encrypted files"*, 19 Aug).

- **Decision 12:** `sgit publish` emits the **plaintext surface only** — loader, cover,
  manifest, key file, optional api docs, self-gitignore. **No ciphertext is copied.** The
  manifest enumerates the store (ids, sizes, sha256); output is O(KB) for any vault
  (measured: 5 files, ~5 KB, for a 22-object store).
- The served root is **composed at deployment**: co-located (one-repo pattern — serve the
  repo, zero copies; the loader fetches `../bare/{fid}`) or assembled (`cp` surface to the
  site root + `bare/` to `api/vault/read/<vid>/bare/`). **Zero-copy composition verified
  live**: real clone against a served repo root's `.sg_vault/` with no projection in
  existence (`06` §2.12).
- `sgit vault serve` composes **virtually** — routes `/api/vault/read/<vid>/bare/*` to
  `.sg_vault/bare/*`. P3 acceptance updated; "stale" redefined as a manifest-hash compare.
- **I1 restated:** the ciphertext a reader receives is byte-identical to the store —
  guarded at the composition step, trivially true for publish (it copies nothing).
- Knock-ons: `10`'s git-dedup measurement (C2) moot — nothing left to dedupe; staleness
  (R4) shrinks to the manifest's listing; the self-gitignore rationale in `07` §4 restated
  (derived output, not duplicate objects); `simulate_publish.py` updated to r9; P2
  retitled "the plaintext surface"; README gains fact 7.

## 2026-08-19 — r8: consistency pass + change control (`a3b4ccf`)

**Trigger:** maintainer review — `01`'s directory structure still showed the pre-19-Aug
`files/…` expansion; asked for a full consistency pass and this file.

- **`--with-plaintext` removed from `sgit publish` everywhere** (the R1 contradiction,
  *fixed* rather than just recorded): `01` §2 diagram and §3 layout, `02` usage line and
  refusal mockup, `04` I5, `05` P4. Expansion is now **decision 11**: a future
  `sgit vault expand` (**P8**, deferred, not v1); its refusal string ships with it.
- **`--force` removed** from the publish usage line (R5 — dead flag since the target
  argument was removed).
- **Visibility-downgrade warning added** (`02` §1, P4 acceptance): a CI runner is always a
  fresh clone and resolves `bare`, so a republish without `--visibility public` would
  silently drop the key file (R3).
- **`manifest.json` `objects[]` entries gain `sha256`** of the ciphertext (`01` §4, P2
  acceptance): the tabletop's keyless mirror could content-verify only 12 of 18 objects,
  because refs/indexes/keys are HMAC/random-named (R6).
- **`.gitignore` joins the declared plaintext surface** (`01` §4, `07` §4, mockup counts in
  `02`): publish writes it, so the audit must list it.
- **`serve` "stale" defined** (P3): projection head-ref bytes ≠ `bare/refs/…` bytes — a
  keyless compare (R4/R7).
- **Deployer table gains two rows** (`07` §5): `.nojekyll` on branch-root Pages deploys
  (Jekyll silently drops dot-directories — F3), and redeploy propagation under Pages'
  `max-age=600`.
- **P2 acceptance:** publish must run with only the read key (proven, tabletop step 9).
- `03` flow 4 no longer shows `sgit publish ./fork-site` (stale target argument).
- **`CHANGELOG.md` created**; README indexes it; `00` requires consulting and updating it.

## 2026-08-19 — r7: executed tabletop + full review pass (`2cedd9a`)

**Trigger:** maintainer asked for a step-back review and an executed tabletop of the
one-repo GitHub Pages scenario.

- Added `10__tabletop__github-pages-one-repo.md` — the flow **ran for real** (real CLI +
  in-memory SG/Send server; publish simulated per spec with real crypto inside).
- Confirmed by execution: I1's git-dedup corollary, I4, I6, both clone layouts, keyless
  custody, the update cycle. New measured facts in README: **a repo committing
  `.sg_vault/bare` is already statically clonable** (no publish step), and **publish needs
  only the read key**.
- Found: R1 (expansion had three owners on paper — fixed in r8), **F2: a refused
  `sgit push` rewrites mutable-ref bytes** (code bug, fix owed), F1 (root `.gitignore` is
  vault content), R2–R9 gaps.
- Lab promoted to `scripts/tabletop__static_publishing/`; `simulate_publish.py` is P2's
  first draft. Review: `…/architect/reviews/08/19/v1__review__static-publishing-full-pass.md`.

## 2026-08-19 — r6: no second loader copy (`ec2ff47`)

**Trigger:** maintainer — *"why do you need the `vault.html` file?"*

- Removed `vault.html`: it guarded a **partial-expansion mode that does not exist**. Fully
  expanded = plain static site, no sgit artefacts; ciphertext-only = loader at the root.
  `manifest.json` still records which file holds the root, with its hash.
- Recorded: if partial expansion is ever introduced, the question returns with it.

## 2026-08-19 — r5: the two `index.html` files separated (`f2ff12d`)

**Trigger:** maintainer — the pack had conflated the **loader**
(`.sg_vault/publish/index.html`, plaintext by design) with the **vault's own root
`index.html`** (encrypted content, *is* the site).

- `publish` never chooses between them: vault content is ciphertext at publish time, so
  `.sg_vault/publish/` holds **no vault content** — safe to commit publicly for any vault.
- Precedence at deployment-time expansion: **the decrypted vault page wins**.
- **Decision 2 re-settled**, I4 restored to its unconditional form; the erroneous
  "your website vault's index.html leaks at `bare`" warning (r4) deleted — at `bare`
  nothing is decrypted, so the scenario cannot occur.

## 2026-08-19 — r4: publish takes no target (`89acc7d`)

**Trigger:** maintainer — *"`.sg_vault/publish` should be the only folder that changes…
it doesn't care where it is published."*

- **Decision 9 settled:** no output-directory argument; one fixed, target-agnostic output.
  Deleted: the realpath containment rule, the `--force`-ancestor hazard, the ignored-path
  escape hatch, the `.sgit/publish/` source-folder proposal and its naming decision.
- **Decision 5 revised:** visibility lives in per-clone local config (a clone must not
  inherit the publisher's deployment settings); fresh clones default `bare`.
- `07` rewritten from a placement ruleset into a description of the output; the folder
  self-ignores via a nested `.gitignore` (`*`); invariant **I6** restated as "publishing
  changes nothing but `.sg_vault/publish/`". Superseded in part by r5 (overrides moved out
  of publish entirely).

## 2026-08-19 — r3: `static.sgit.ai` answered (`65ebfbd`)

**Trigger:** maintainer proposed a first-party static asset site (Pages) for Swagger JS,
logos, pinned dependencies.

- Added `09__asset-origin.md`; **decision 10**: yes to the asset origin — on
  **S3/CloudFront, never Pages** (Pages pins `max-age=600`, measured), and only as a
  **publish-time** source (primary for `--api-docs=bundled`, jsdelivr fallback, same SRI
  pin). Never on a reader's critical path: a read-time first-party origin would be a beacon
  every vault reader pings.

## 2026-08-18 — r2: work-tree publishing forbidden; Swagger flips to CDN (`27674bb`)

**Trigger:** maintainer — `sgit publish ./site` must not be allowed (output becomes vault
content); Swagger UI should be loadable from a CDN.

- Created `07` (first version): containment rule + `.sg_vault/publish/` default — the
  amplification loop named (publish → push → publish doubles the store). Superseded by r4's
  simpler answer.
- **Decision 7 reversed:** CDN+SRI becomes the default (`--api-docs` ⇒ `=cdn`), vendoring
  the opt-in. Measured: UI = 1,604,824 B ≈ 2.7× a whole measured vault; SRI + exact pin +
  `no-referrer` + CSP close the compromised-CDN path. sgit ships no UI bytes; `=bundled`
  fetch-verifies against the same hashes. Evidence `06` §2.8; invariant **I6** introduced.

## 2026-08-18 — r1: published API docs (`cab05a8`)

**Trigger:** maintainer — *"what about adding swagger support to that `/api/*` static
folder… an optional parameter on `sgit publish`."*

- Added `08__api-docs.md`: two artefacts (`api/openapi.json`, a few KB generated from
  `manifest.json`; `api/docs/` Swagger UI), flags `--api-spec` / `--api-docs`, the
  same-origin/stored-key interaction, phase **P4b**, decisions 7 & 8 (7 reversed in r2).

## 2026-08-17 — r0: the pack (`1f70fa0`)

Split the single dev-pack monolith into files `00`–`06`: dev brief, architecture (transport
seam, publish-as-projection, manifest contract, plaintext allow-list), commands & UX,
flows, 5 invariants + 14 test cells, phases P1–P7, six decisions + the measured evidence
base (Pages CORS, custody-needs-manifest, unlinkable forks, four read-path dependencies,
bundle economics, static clone proven against live Pages).
