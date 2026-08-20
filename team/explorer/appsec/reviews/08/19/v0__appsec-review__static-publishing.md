# AppSec review — static-publishing feature set (design-stage)

**Reviewer:** Explorer AppSec · **Date:** 2026-08-19 · **Target branch:**
`claude/sgit-architect-agent-review-3tl5ti` · **Pack:**
`team/explorer/dev/impl-plans/08/17/static-publishing/` at r12 (per `CHANGELOG.md`).

**Status of the thing under review:** design-stage. `sgit publish` (P2/P4/P4b),
`sgit vault serve` (P3), `sgit vault mirror` (P5) and `sgit vault attach` (P9) are **not
built**; the static read transport is a spike (`scripts/spike__static_vault_transport.py`),
not shipped code, and the read-only clone path it will be promoted from **is** shipped and
was inspected here. Most findings are therefore spec-level; where behaviour already exists
in code it is cited by `file:line` and marked CODE, and the rest are marked SPEC or
REASONED.

---

## 1. Executive summary

This is a careful, self-critical design. The pack has reversed its own load-bearing
decisions a dozen times in three days and the reversals are legible; the invariants I1–I6
are mostly the right ones; the crypto substrate (`Vault__Crypto`) is sound and the key
formats/classifier already shipped are a genuinely good idea. The zero-knowledge property —
the server never needs the key — holds structurally for the *live* API and is preserved by
the static transport. Nothing here changes a wire or key format, and the highest-blast-radius
mistake (publish copying ciphertext, or widening the plaintext surface from vault content)
has been designed out rather than merely policed.

The gap that runs through the whole feature is **the absence of a root of trust at read
time.** A published static vault is a folder on a host the reader does not control, and
every integrity claim in it — the manifest's hashes, the object list, the head ref, the key
filename, the loader bytes — is *self-attested by that same folder.* The design leans on
"the object id is `sha256(ciphertext)`, verifiable with no key" as its integrity anchor, and
that anchor is real but (a) it is **not actually checked in the code that will ship**, and
(b) it only covers the ~⅔ of objects that are content-addressed, not refs/indexes/keys, and
not freshness. Against a passive or read-only-malicious host the confidentiality guarantee
(AES-256-GCM) holds regardless; against an *active* malicious host the design currently
offers no way for a reader to tell a genuine, current vault from a coherent forgery or a
coherent rollback. For a "public handbook" that is an acceptable, documentable risk; for the
private-vault and CI tiers it deserves an explicit decision rather than silence.

### Verdict

**Proceed to build P1 and P3, with two must-fix items folded in before P2/P5 ship, and one
maintainer decision (freshness/authenticity) opened before the private-vault and CI stories
are promoted from "tabletop" to "supported".** Nothing here blocks the public-vault use
case, which is the one the tabletops actually exercised. The private-read and CI-runner
tiers are carrying security weight the pack has not yet priced.

### Top 5 risks

1. **SP-1 (High, CODE):** the shipped clone path writes fetched objects to disk with **no
   `sha256(ciphertext) == id` verification** (`Clone__Workspace.save_file`,
   `Clone__Workspace.py:52`), directly contradicting `00` §3 ("Verify what you fetch… Do it
   unconditionally") and the flow diagram in `03` §2 that claims "verify sha256(ciphertext)==id".
   The only integrity backstop is the AES-GCM tag at decrypt time. P1 promotes this path.
2. **SP-2 (High, SPEC):** **no freshness anchor.** A malicious host, or an HTTP MITM on a
   non-TLS target, can serve a *previously valid* coherent site — old ref, old head, old
   manifest — and no reader (browser, CLI, or mirror) can detect the rollback/freeze. This
   is the classic TUF freeze attack and the design has no counter to it.
3. **SP-3 (High, SPEC):** **the manifest is authority for the two consumers that cannot fall
   back.** The CLI honours "hint, never authority" by parent-walking loose objects, but the
   keyless mirror's *only* integrity signal is the manifest's self-attested `sha256`, and the
   browser loader's object list comes from the same self-attested manifest. A host that
   rewrites object + manifest hash together produces a mirror that "verifies" corrupt bytes.
4. **SP-4 (Medium-High, SPEC):** the **vault→work-tree→repo path lets a vault collaborator
   ship CI code and reader-facing HTML.** The pack accepts (r11 step 3, "policy: ACCEPTED")
   that a `.github/workflows/*.yml` swept into the vault as content travels to every clone
   and lands in the publisher's repo. A collaborator with vault *write* access thereby gains
   *arbitrary-code-execution on the publisher's CI runner* — which for a private vault is
   the one service holding the read key.
5. **SP-8 (Medium, SPEC/CODE):** **manifest-driven path traversal in `mirror`/compose.**
   `manifest.objects[].file_id` is attacker-influenced and is used both to fetch and to
   *write* files. P5's acceptance criteria do not require routing those writes through
   `Vault__Path_Guard` (which exists and is correct). A `file_id` of `../../etc/cron.d/x`
   must be rejected, and nothing in the spec yet says it is.

---

## 2. Scope and method

**In scope:** the full static-publishing pack (`00`–`11`, `templates/github-pages.yml`,
`CHANGELOG.md`) and the load-bearing code it builds on: `Vault__Crypto`, `Vault__Ignore`,
`Vault__Path_Guard`, `Vault__Backup`, `Vault__Sync__Clone` and the clone workflow steps,
`Vault__Object_Store`, and the transport spike. Personas A–J from the brief plus what fell
out beyond them.

**Method:** read every pack file at r12; verified each behavioural claim against code where
the code exists (read-only inspection; no files outside this document were modified, nothing
was committed or pushed, no external host was contacted). Claims are tagged **verified-in-code**
(`file:line`), **verified-in-doc** (`NN §`), or **REASONED** where I am arguing about a
design that has no code yet. I did not execute the test suite; the tabletops (`10`, `11`)
are taken as executed evidence per their own labelling, and I re-derived their security
consequences rather than re-running them.

**Confidence caveats:** the browser loader is explicitly out of this repo (Web team owns its
JavaScript, `00` §6), so every loader claim is REASONED from the spec, not verified. `serve`,
`mirror`, `publish`, and `attach` do not exist, so findings against them are against their
specified acceptance criteria.

---

## 3. What the design gets right

Credit where the pack has already done the work — this is not boilerplate, these are the
decisions that make the rest of the review short.

- **Classification by declaration, not shape** (`Vault__Crypto.classify_key`,
  `Vault__Crypto.py:86-103`). A read-only surface refusing a `sgit_private_vault_` key is
  enforced by prefix, and the loader is told to port the same primitive rather than
  re-guess. The comment history ("guessing from shape is what once misrouted a 64-hex
  passphrase") shows this was learned, not assumed. Correct and load-bearing.
- **The plaintext surface is a fixed allow-list of names in code, never a pattern, never a
  folder emitted wholesale** (`01` §5, `00` §3). This is the single most important control
  in the feature and it is stated crisply and repeatedly: a vault collaborator cannot widen
  the plaintext surface by naming a file, because `publish` never reads vault content to
  decide what to emit. I tried to break it (see SP-4) and could only do so through the
  *deployment-time expansion* path, which the pack has already fenced off into a deferred,
  key-holding command (P8).
- **Publish copies no ciphertext (r9, decision 12).** Removing the projection removed an
  entire class of "the copy and the store disagree" bugs and made I1 true by construction.
- **Generated passphrase entropy is strong.** `Vault__Sync.generate_vault_key`
  (`Vault__Sync.py:36-40`) draws a 24-char passphrase from a 36-symbol alphabet via
  `secrets.choice` — ~124 bits from a CSPRNG — and PBKDF2-SHA256 at 600k iterations
  (`Vault__Crypto.py:13`) sits on top. For generated keys, offline brute force is a non-issue.
- **The key-in-filename convention is reasoned, not accidental** (`01` §3): public only,
  prompt-gated, and the pack explicitly forbids carrying the pattern across to private read
  keys "by analogy". The `sgit_public_read_` vs `sgit_private_read_` word-not-character
  distinction (`Vault__Crypto.py:52-60`) is a deliberate defence against scanner training.
- **`Vault__Path_Guard` is genuinely good** (`Vault__Path_Guard.py`): rejects absolute
  paths on both platforms, `..` on both separators, and re-checks the resolved prefix; the
  comment about not normalising the join path is exactly right. The tool the feature needs
  already exists — the finding (SP-8) is that the spec doesn't yet require its use.
- **The canonical `.gitignore` guards key material, keyed-backup hazard included**
  (`07` §4, decision 13, verified against `Vault__Backup.py:128-131` — `--include-key`
  writes the vault key as `VAULT-KEY` into the zip under `.sg_vault/backups/`). The pack
  caught that `local/`-only was insufficient and corrected it. Right call, correctly grounded.
- **F5 (dead host ≠ empty vault), F6 (attach mode-exclusivity), F7 (refs-checkout after
  push) are real findings already recorded** with the right fixes. I am not re-reporting them.

The invariants I1–I6 and findings F1–F7 are, with the exceptions called out below (SP-1
sharpens the "verify" claim behind I-none-explicitly; SP-3 sharpens the I3 custody story;
SP-4 sharpens F1), sound. This review is mostly about what sits *outside* the invariant set.

---

## 4. Findings table

| ID | Sev | Persona | Component | Kind | One line | Gate |
|---|---|---|---|---|---|---|
| SP-1 | High | A,F | clone/download path | CODE | Fetched objects written with no `sha256==id` check; contradicts `00` §3 and `03` §2 | **must-fix before P1 ships** |
| SP-2 | High | A,C | transport / manifest | SPEC | No freshness anchor — coherent rollback/freeze undetectable | **decision before private/CI promoted** |
| SP-3 | High | A,F | manifest consumers | SPEC | Manifest is de-facto authority for mirror + browser; self-attested hashes | **must-fix before P5 ships** |
| SP-4 | Med-High | B,E | vault→repo→CI path | SPEC | Collaborator ships CI workflow + reader HTML via vault content | **decision before P9/CI** |
| SP-5 | Medium | B,D,G | loader localStorage | SPEC | Stored key readable by any script on origin, incl. expanded collaborator HTML | before P4 loader work |
| SP-6 | Medium | C,G | fragment + http clone | SPEC/CODE | Private read key leak channels; CLI clones over `http://` with key on argv | before P4 / P1 |
| SP-7 | Medium | J | transport tiers | SPEC | Static fallback silently drops revocation/auth/audit the live API had | before P4 |
| SP-8 | Medium | F | mirror / compose | SPEC/CODE | Manifest `file_id` path traversal on write; guard not required by P5 | **must-fix before P5 ships** |
| SP-9 | Medium | I | `serve` | SPEC | No `Host`-header check → DNS-rebinding; `--bind 0.0.0.0` footgun | before P3 |
| SP-10 | Medium | D,E | workflow template | SPEC | Actions unpinned by SHA, `pipx install` unpinned in shipped template | before decision-15 generator |
| SP-11 | Low | D | api-docs CDN | SPEC | CSP is "optional/belt-and-braces"; should be mandatory on the docs page | P4b |
| SP-12 | Low-Med | A,H | manifest metadata | SPEC | bare-visibility manifest leaks estate shape; no notice at bare | P2/P4 |
| SP-13 | Low | G | user-supplied keys | CODE | PBKDF2 is sole guard for weak *user-chosen* passphrases; kdf cache residency | later |
| SP-14 | Med | A | full-site substitution | SPEC | No binding vault_id↔key↔content authenticity; whole-site forgery undetectable | rolls into SP-2 decision |
| SP-15 | Info | H | vault_id | CODE | 8-char id in URLs/logs; enumerable on a listing host | accepted |

---

## 5. Detailed findings

### SP-1 — The clone path does not verify what it fetches (High, CODE)

**Claim under test.** `00` §3 (non-negotiable constraints): *"Verify what you fetch. Object
ids are `sha256(ciphertext)[:12]`, so every object can be checked with no key and no trust in
the host. Do it unconditionally."* `03` §2's static-clone sequence diagram literally shows
the CLI step *"decrypt · verify sha256(ciphertext)==id · checkout"*.

**What the code does.** The read-only clone (`Vault__Sync__Clone.clone_read_only`,
`Vault__Sync__Clone.py:61`) runs `Workflow__Clone__ReadOnly`, whose download steps
(`Step__Clone__Download_Blobs.py`, `Step__Clone__Walk_Commits.py:35`) call
`workspace.save_file(...)`. `Clone__Workspace.save_file` (`Clone__Workspace.py:52-57`) is, in
full, `os.makedirs` + `open(...,'wb').write(data)`. There is **no** call to
`Vault__Object_Store.verify_integrity` (`Vault__Object_Store.py:93`) or `compute_object_id`
anywhere in `sgit_ai/workflow/clone/` (grep confirms zero hits). The verification method
exists and is correct; it is simply never invoked on the read path. The flow diagram in
`03` §2 documents a check the shipped code does not perform.

**Attack scenario.** A malicious or compromised static host (persona A) serves, for a
requested `bare/data/obj-cas-imm-<id>`, a *different* byte string. Two sub-cases:
- *Garbage / bit-flipped ciphertext:* AES-256-GCM decryption fails the tag check
  (`Vault__Crypto.decrypt`, `Vault__Crypto.py:283-287`) and the clone aborts. Integrity is
  preserved here — but by the cipher, not by the id check the design claims, and the failure
  is an opaque crypto error, not "host served the wrong object for id X".
- *A different, validly-encrypted object from the same vault:* the id is not checked, so the
  substitution is invisible at the CAS layer; whether it is caught downstream depends
  entirely on where the object is referenced and whether *that* reference's key derivation
  rejects it. Relying on "it'll probably fail to decrypt in context" is exactly the trust in
  the host the design says it does not extend.

The non-content-addressed objects make this worse (see SP-3): refs (`ref-pid-muw-…`),
indexes (`idx-pid-…`) and PKI keys (`key-rnd-imm-…`) are HMAC- or random-named, not
`sha256(ciphertext)`, so there is *no* id to check them against even in principle. For those
the GCM tag under the structure key is the only integrity, and a rollback to an
older-but-valid ref is not a tag failure at all (SP-2).

**Why it matters now.** P1's entire job is to "promote the spike; do not redesign it"
(`05` P1). The spike (`spike__static_vault_transport.py`) also does no verification. If P1
ships as specified, the "verify unconditionally" constraint ships violated, and the flow
diagram becomes documentation of a control that isn't there — the worst kind, because
reviewers will cite it.

**Mitigation.** Make `save_file` (or the step that calls it) verify, for every
`obj-cas-imm-*` id, that `compute_object_id(data) == id` before writing, failing that object
soft (per-object, per `00` §3's fail-soft rule) with a message that names the host and the
id. For non-`obj-cas-imm` ids, verify against the manifest hash *only as a hint* and record
that they are not independently verifiable (SP-3). Add a >0-object fixture where the host
returns a wrong-but-valid object and assert the clone rejects it.

**Lands in:** `05` P1 acceptance (a new criterion), `04` (an invariant — arguably a 7th:
"every content-addressed object is id-verified on read"), and a correction to the `03` §2
diagram if verification is deferred. **Gate: must-fix before P1 is called done.**

---

### SP-2 — No freshness anchor: rollback and freeze are undetectable (High, SPEC)

**The property that is missing.** Nothing in a published vault binds a reader to *current*
state. The head is a mutable ref (`ref-pid-muw-…`, "muw" = mutable) fetched like any other
object and decrypted with the structure key; the manifest records a `head` and a `commits`
list but is itself a plaintext file served by the same host. A host that keeps a byte-exact
copy of yesterday's site — old ref, old manifest, old objects — serves a fully coherent,
fully verifying, stale vault. Every hash matches (they are yesterday's hashes); every
signature matches (there are none); the GCM tags all pass (that ciphertext was validly
produced yesterday). The reader has no way to know.

**Attack scenarios.**
- *Freeze (persona A, malicious host):* a vault publishes a security advisory as commit N+1;
  the host continues serving commit N. Readers who clone or browse see the pre-advisory
  state indefinitely. `11` step 7 already documents that "the site follows the repo
  timeline" and rollback is a `git revert` — but that is the *author's* rollback. This is
  the *host's* rollback, done without the author, and the pack does not treat it.
- *Freeze via cache (persona C / infrastructure):* Pages stamps `max-age=600` on everything
  (`07` §5, `10` step 8), so even an honest deployment shows a ~10-minute-stale head. That
  is benign, but it establishes that readers already tolerate an unknown-staleness window;
  an attacker's freeze is the same phenomenon with the clock removed.
- *Rollback on HTTP (persona C, MITM):* if the target is `http://` (the CLI transport
  accepts it — SP-6), a network attacker substitutes an older coherent snapshot with no host
  compromise at all.

**What a keyless mirror cannot help with.** Custody (I3) gives you *a* verifiable copy, not
*the current* copy. Two archivists mirroring at different times, or through different hosts,
have no protocol to agree on which is newer — the `commits` list length is host-attested and
a freeze attacker simply serves the shorter one.

**Is there a fix worth recommending?** Yes, and it is worth an explicit decision rather than
an accepted-risk shrug, because the building blocks exist:

- The vault already has a PKI (`bare/keys/key-rnd-imm-*`, `PKI__Crypto`). A **signed head**
  — the author signs `(vault_id, head_commit_id, monotonic_counter, timestamp)` with a vault
  signing key whose *public* half is published in `cover.json`/`manifest.json` — lets any
  reader verify that the head they were served was blessed by the writer, and a **monotonic
  counter** lets a reader who has seen counter=7 reject a later fetch of counter=5. This
  defeats rollback for anyone who has ever seen a newer state, and defeats forgery outright
  (SP-14). The cost is that the signing key must *not* be the read key (the host has that for
  public vaults) — it must be a separate secret the writer holds, which the PKI already
  provides.
- A weaker, cheaper option: publish a **signed timestamp / expiry** in the manifest so a
  frozen site becomes *detectably* old after a bounded window (TUF's timestamp role). Still
  needs a writer-held signing key.
- Neither defeats a *first-view* forgery by a host that has never served the genuine vault
  (there is no trust root but the URL) — that is SP-14, and only out-of-band publication of
  the vault's public key closes it.

**Mitigation / disposition.** For **public** vaults where the host already has everything, a
signature by a *separate* writer key still buys rollback/forgery detection (the host cannot
forge the signature even though it can read the content). Recommend: (1) document the
non-guarantee explicitly today — "a static host can serve a stale but coherent snapshot;
freshness is not guaranteed without the live API"; (2) open a maintainer decision for a
signed, monotonic head before the **private-read and CI tiers** are promoted from tabletop
to supported, because those tiers imply a trust in the host that public-handbook browsing
does not.

**Lands in:** a new decision (call it 16) in `06` §1; a non-guarantee paragraph in `01` §1
and `02`; and, if adopted, a manifest field + `cover.json` public-key field spec in `01` §4.
**Gate: decision required before private/CI tiers ship; accepted-risk (documented) for the
public tier in the interim.**

---

### SP-3 — The manifest is de-facto authority for the two consumers that cannot fall back (High, SPEC)

`01` §4 and the README fact 2 are careful: the manifest is *"a hint, never authority; a
client that distrusts it falls back to the parent walk over loose objects."* That is true and
verifiable for the **CLI reader with a read key** — it can ignore the manifest entirely,
walk parents from the ref, and id-verify content-addressed objects (once SP-1 is fixed). But
two of the three reader types named in the brief cannot fall back:

- **The keyless mirror (persona F, I3).** By construction it has no key, so it cannot decrypt
  the ref, cannot walk the tree, and cannot learn a single filename except from the manifest
  (README fact 2 makes exactly this argument for why the manifest is *mandatory*). Its only
  integrity signal is `manifest.objects[].sha256`. For the ~⅓ of objects that are
  `obj-cas-imm-*` it *could* recompute `sha256(ciphertext)[:12]` and compare to the id in the
  filename — self-verifying, no manifest trust needed. But `10` step 7 and `01` §4 describe
  the mirror trusting the manifest's `sha256` for the refs/indexes/keys it *cannot*
  content-address. A host that rewrites an object *and* its manifest `sha256` in lockstep
  produces a mirror that reports "verified" over corrupted or attacker-chosen bytes. The
  mirror's "custody without access" is really "custody of whatever the host chose to serve,
  labelled verified."
- **The browser loader (persona A/D, REASONED — Web team code).** Its object list and the
  key-file glob come from the same self-attested folder. A malicious manifest can *omit*
  objects (a selective-withholding / partition attack: hide the commit that revoked a
  credential), *reorder* the commit list, or point `head` at an older commit (SP-2 again).

**Concrete manifest attacks to enumerate (persona F):**
- *Withholding:* drop `objects[]` entries or truncate `commits[]` → reader/mirror silently
  gets a partial vault and, absent SP-1's id check and a signed commit count, cannot tell.
- *Inflation / zip-bomb-ish:* an entry with a huge `size` or thousands of duplicate
  `file_id`s → a naive mirror pre-allocates or fetches unboundedly. P5 must bound object
  count and per-object size against sane limits and dedupe `file_id`.
- *Duplicate / conflicting entries:* two `objects[]` with the same `file_id` and different
  `sha256` → undefined which wins; define it (reject the manifest).

**Mitigation.**
- For `obj-cas-imm-*` objects, the mirror and the CLI must **recompute the id and ignore the
  manifest `sha256`** — the id *is* the hash, trusting the manifest for it is strictly
  weaker. State this in `01` §4 and `05` P5.
- For non-content-addressed objects (refs/indexes/keys), the manifest `sha256` is *not*
  independent integrity — say so explicitly, and make it a signed field if SP-2's signing is
  adopted (then the mirror verifies the signature, not the host's word).
- P5 acceptance must bound counts/sizes, dedupe `file_id`, and reject conflicting entries.

**Lands in:** `01` §4 (the "hint never authority" paragraph needs a sentence on *which
consumers can actually exercise the fallback*), `05` P5 acceptance, `04` I3's assertion
(strengthen: mirror recomputes ids; a manifest with a wrong `sha256` for an `obj-cas-imm`
object is *detected*, not trusted). **Gate: must-fix before P5 ships.**

---

### SP-4 — Vault write access escalates to CI code execution and reader-facing HTML (Medium-High, SPEC)

The one-repo pattern's power is also its exposure. Two paths, both flowing from *vault write
access* (persona B) to things a vault should not control:

**(a) The workflow-in-the-vault path.** `11` step 3 records that a `.github/workflows/pages.yml`
placed in the work tree is *"swept into the VAULT as content (F1 generalised)"* and the
policy is *"ACCEPTED — deploy config travels with clones,"* demonstrated by the reader's
clone arriving carrying `pages.yml`. Follow the consequence: a **collaborator with vault
write access** commits a modified `.github/workflows/*.yml`. On the next `sgit pull` + `git
add -A` + push by the *publisher* (which the one-repo flow encourages — `10` step 8's update
cycle is exactly `sgit commit && sgit push && git add -A && git commit && git push`), that
workflow lands in the publisher's GitHub repo and runs on the publisher's runner with the
publisher's secrets. For a **private** vault that runner holds `SGIT_READ_KEY` as a repo
secret (`templates/github-pages.yml:41-44`, `11` step 10 — *"the one key-holding service in
the whole model"*). The collaborator has thereby escalated *vault write* into *read-key
exfiltration and arbitrary code execution in the publisher's CI.* The vault's threat model
says a writer can change content; it does not say a writer can run code on the publisher's
infrastructure, and in the one-repo pattern it silently can.

This is not the same as "a collaborator can change the site" (expected). It is "a
collaborator can change the *pipeline that deploys the site and holds the key*."

**(b) The expanded-HTML path.** A vault's own `index.html` is content (`07` §3). When a
deployer *expands* plaintext (P8, deferred) or simply commits the hydrated work tree (the
one-folder pattern *is* the expansion, `02` §1), that collaborator-authored HTML is served
same-origin with the loader and any stored key (SP-5). A hostile `index.html` reads
`localStorage`, or phishes a private read key from a reader who pastes it, and beacons it
out. The reader believes they are on the publisher's site; they are on the publisher's
origin running the collaborator's script.

**Mitigations.**
- Treat `.github/` (and other CI-config paths — `.gitlab-ci.yml`, `.circleci/`,
  `azure-pipelines.yml`) specially in the one-repo guidance: either the deploy workflow is
  **not** vault content (kept out of the vault via the canonical ignore set, accepting the
  desync the pack worried about) or the docs must state, loudly, that **granting vault write
  access grants CI-config write access, i.e. runner code execution**, in the one-repo
  pattern. The pack "ACCEPTED" the travel of the file; it did not price the escalation.
- The runner must run with the **least privilege** that works: for a private vault, the read
  key as a secret is unavoidable, but the workflow should have `contents: read` only (it
  does — `templates/github-pages.yml:14-17`, good), should not expose the secret to steps
  that run vault-authored code, and should consider requiring the deploy workflow to live on
  a protected branch that collaborators cannot alter.
- The loader must not persist keys where vault-authored HTML can read them (SP-5).
- Fork-PR handling is already correct (`11` step 5, `templates/github-pages.yml:41-43`
  skip-when-no-secret) — keep it, and add `pull_request_target` to the list of things the
  generator must never emit (it would run fork-authored workflow code *with* secrets).

**Lands in:** `07` §4/§5 (the CI-config-is-vault-content escalation), `11`/`06` decision 15
(the generator's least-privilege posture and the `pull_request_target` prohibition), `02`
(a one-repo "who can run code on your runner" note). **Gate: decision before P9/CI is
promoted.**

---

### SP-5 — Loader key persistence is same-origin-readable by any served script (Medium, SPEC)

`08` §4 analyses this for the Swagger docs page and correctly concludes the root fix belongs
in the loader ("If the loader keeps keys in memory for the session and never writes them to
`localStorage`, the same-origin objection collapses"). The finding here is that the analysis
is scoped too narrowly: it is framed as a Swagger-UI concern, but the exposed surface is
**every plaintext file on the origin**, including the vault's own expanded `index.html`
authored by a possibly-hostile collaborator (SP-4b) and any `api/docs/` page. A private read
key in `localStorage`, scoped to origin not path, is readable by all of them.

For a **public** vault the key is public — no loss. For a **private** vault browsed with a
private read key via the loader's "remember this key on this device" option, on a host that
also serves attacker-influenceable HTML, the stored key is exfiltratable.

**Mitigation.** Raise as a firm loader-design requirement to the Web team (it is their code,
`00` §6): private read keys are **session-memory only, never `localStorage`**; if
persistence is offered at all it is public-key-only and gated on the `sgit_public_read_`
classification the loader already computes (`01` §7). Document that a published origin may
serve scripts the publisher did not author, so the loader must assume a hostile same-origin
neighbour.

**Lands in:** `02` §5 (loader mockups / behaviour notes) and a one-line requirement in `01`
§7, flagged to the Web team. **Gate: before P4 loader work.**

---

### SP-6 — Private-read leak channels: URL fragment and `http://` clone (Medium, SPEC/CODE)

Two related channels for the *private* read tier (persona C, G):

**(a) Fragment handling (browser).** The design puts the private key in the URL `#fragment`
(`01` §7), which is correct — fragments are not sent in `Referer`, not logged server-side,
not in the query. But fragments *are* in browser history, in the address bar, in
clipboard-shared links, and are preserved across some same-origin redirects. If the loader
ever (i) writes the full URL somewhere, (ii) triggers a navigation that carries the
fragment, or (iii) is itself loaded via a redirect chain, the key can escape. This is Web-team
territory but must be a stated requirement: strip the fragment from `window.location`
immediately on read (the flow in `01` §7 says "strip fragment · open vault" — good, make it a
hard requirement and test it), never reflect it into a link or `history.pushState`, and set
`referrerpolicy=no-referrer` document-wide, not just on the Swagger tags.

**(b) `http://` clone (CLI, CODE).** The transport resolves `http://` and `https://`
identically (`spike__static_vault_transport.py:44`, `_is_local` treats both as remote; the
resolution table in `01` §1 and `03` §5 branches only on "http(s)://"). A user running
`sgit clone sgit_private_read_<hex>:<vault_id> http://host/...` sends nothing secret to the
host (I2 holds — the key is never in the request), but: the *ciphertext* and the *which-vault*
metadata cross the wire in clear, a MITM can rollback/substitute (SP-2), and the key sits in
shell history and the process table (`ps`) as an argv. The pack never warns about `http://`.

**Mitigation.** (a) Make the fragment-hygiene rules explicit loader requirements with tests.
(b) For the CLI: warn (not block) on `http://` for any read that carries a private key, and
document that read keys on the command line land in shell history — recommend an env var or
a key file for private reads, mirroring how the public path already avoids argv. Consider
refusing `http://` for `sgit_private_read_` unless `--insecure-transport` is passed.

**Lands in:** `01` §7 (fragment requirements), `02` §2 (an `http://`+private-key warning
string), `05` P1 acceptance (an `http://` warning). **Gate: before P4 / alongside P1.**

---

### SP-7 — Static fallback silently drops security properties the live API had (Medium, SPEC)

Persona J. The transport-resolution logic (`01` §1, `03` §5) silently falls back from the
authenticated live API to the anonymous static transport on `404/405/501/CORS`. The pack
frames the *loss* as "read-only, no writes" and reports the resolved transport (good — "visible
≠ silent"). But the live API plausibly enforces more than write-blocking: **token checks on
reads, server-side access revocation, per-reader authorization, rate limiting, and read
audit logging.** A vault reachable both live and static loses *all* of those on the static
path, and the fallback is automatic. Two concrete consequences:

- **Revocation cannot exist on a static host.** `06` §2.4 records this for the git-history
  case ("a public-repo static vault cannot revoke read access even with the write key"). The
  general statement is broader and belongs stated once: *publishing to any static host
  converts "access controlled by the server" into "access controlled by possession of the
  read key, forever, unlogged."* Rotating the key = re-keying = a new vault at new paths
  (`03` §4, `06` §2.4) — the old published bytes remain readable by anyone who fetched them.
- **A "named" (bare) vault is not "private" in the access-controlled sense.** The three
  visibility tiers (bare/named/public) describe *what the publisher put in the folder*, not
  *who may read it*. A bare vault on a public host is readable by anyone who obtains the read
  key through any channel, with no server to say no. The UX should not let "bare" read as
  "access-controlled."

**Mitigation.** Add a short "what the static transport does *not* do that the live API does"
table to `01` (drop: writes, revocation, per-reader auth, read audit, rate limiting). Make
`sgit vault info`'s transport line, or the publish output, state plainly for non-public
vaults that access is now "key-possession, unrevocable, unlogged." This is mostly
documentation, but it is the difference between an informed and an accidental disclosure.

**Lands in:** `01` §1 (a properties-dropped table), `02` §1 (publish output wording for
bare/named). **Gate: before P4 (visibility) ships.**

---

### SP-8 — Manifest-driven path traversal in mirror and compose (Medium, SPEC/CODE)

Persona F. `manifest.objects[].file_id` is a host-controlled string (e.g.
`"bare/refs/ref-pid-muw-…"`). `mirror` (P5) fetches each and **writes it into `./mirror/`**;
the composed-deploy step (`01` §3, `templates/github-pages.yml:51-54`) `cp -r`s the store;
and `serve` (P3) maps request paths to `.sg_vault/bare/*`. Wherever an attacker-influenced
`file_id`/path becomes a *write* target or an *open* target, traversal is possible:
`"file_id": "../../../../etc/cron.d/x"` or an absolute path or a Windows `..\\`.

`Vault__Path_Guard` (`Vault__Path_Guard.py`) already defeats exactly this and is used by the
existing tree-extraction path. The gap is that **P5's acceptance criteria (`05` P5) do not
mention it**, and the compose step in the workflow is a bare `cp -r` with no guard at all.
`serve`'s P3 acceptance *does* require path-guarding (`05` P3, `02` §2) — good — but it must
also guard the *virtual* `api/vault/read/<vid>/bare/*` → `.sg_vault/bare/*` route mapping,
where a crafted request path (`GET /api/vault/read/<vid>/bare/../../../../local/vault_key`)
must not escape `bare/`.

**Mitigation.** P5 must route every manifest `file_id` through `Vault__Path_Guard.safe_join`
before fetching or writing, reject anything that fails (per-object, fail-soft), and cap the
object count/size (SP-3). P3 must guard the virtual route mapping, not just the physical
docroot. The composed-deploy `cp -r` is deployer-owned, but the generator's workflow should
compose from `.sg_vault/bare` (a fixed, trusted local path) rather than from manifest-named
paths — which it does today, so the workflow itself is fine; the exposure is `mirror`.

**Lands in:** `05` P5 acceptance (path-guard requirement), `05` P3 acceptance (guard the
virtual route), `04` (a traversal cell for mirror, reusing the existing payloads). **Gate:
must-fix before P5 ships.**

---

### SP-9 — `serve`: DNS rebinding and the `--bind 0.0.0.0` footgun (Medium, SPEC)

Persona I. `serve` binds `127.0.0.1` by default (decision 4, `05` P3) — correct — and
`--bind` widens loudly. Two residual issues:

- **No `Host`-header validation → DNS rebinding.** A `ThreadingHTTPServer` bound to
  `127.0.0.1` still answers requests whose `Host:` is an attacker domain that has been
  rebound to `127.0.0.1`. A web page the user visits can then `fetch()` the served vault. For
  a **public** vault the content is public anyway; the real exposure is a **private** vault
  served locally with the reader's key in play, or the loader's stored key. Mitigation:
  validate the `Host` header against `127.0.0.1`/`localhost[:port]` and reject others — a few
  lines, stdlib-only, no new dependency.
- **`--bind 0.0.0.0` is a bigger footgun than the wording implies.** "read-only, no listing"
  limits the blast radius, but a private vault served on `0.0.0.0` exposes its ciphertext to
  the LAN, and if the loader is opened with a key on that origin the key is in play. The
  "says so loudly" requirement should specifically say *what* is exposed (this vault's
  objects, to anyone on your network), not just that the bind widened.

**Mitigation.** Add `Host`-header validation to P3's acceptance; sharpen the `--bind`
warning string. Neither adds a dependency.

**Lands in:** `05` P3 acceptance, `02` §2 (`--bind` warning wording). **Gate: before P3
ships.**

---

### SP-10 — The shipped workflow template pins nothing (Medium, SPEC)

`templates/github-pages.yml` is a committed artifact (decision 15's generator output) and it
uses **mutable tags**: `actions/checkout@v4`, `actions/upload-pages-artifact@v3`,
`actions/deploy-pages@v4`, and `pipx install sgit-ai` with no version. The comments say "pin
by SHA in production" and "pin the version in production" (`templates/github-pages.yml:23,24`)
— but the file *is* the production template the generator will emit, and a comment is not a
pin. For a **private** vault, this runner holds the read key; a compromised action tag or a
malicious `sgit-ai` release (persona D/E, supply chain) exfiltrates it.

**Mitigation.** The decision-15 generator should emit **SHA-pinned** actions and a
**version-pinned** `pipx install sgit-ai==X.Y.Z` (or `--index-url` to a trusted mirror), and
the committed template should model that rather than model the insecure form with a comment.
Add `persist-credentials: false` to the checkout (so the `GITHUB_TOKEN` is not left in the
runner's git config for vault-authored steps — ties to SP-4). Consider hash-pinning
`sgit-ai` via `pip install --require-hashes`.

**Lands in:** `templates/github-pages.yml` and `06` decision 15 (the generator's pinning
requirements). **Gate: before the generator (P-future) emits real workflows; the committed
template should be fixed now so it is not copied as-is.**

---

### SP-11 — The docs-page CSP is described as optional (Low, SPEC)

`08` §4 lists a CSP `<meta>` as item 4 with "belt and braces, and free," and the acceptance
criteria (`08` §7) assert the five attributes including CSP — so it *is* required in the
checklist, but the prose frames it as optional hardening. Given the same-origin key-store
concern (SP-5), the CSP (`script-src 'self' https://cdn.jsdelivr.net; connect-src 'self'`)
is the one control that stops an injected script from *exfiltrating* a key even if it runs.
It should be described as load-bearing, not belt-and-braces, and `connect-src 'self'` should
be on the **loader** page too, not only the docs page — that is where keys actually live.

**Mitigation.** Reframe CSP as required on both loader and docs pages; state that
`connect-src 'self'` is the exfiltration backstop for SP-5. **Lands in:** `08` §4, and a new
loader requirement in `01` §7. **Gate: P4b / P4.**

---

### SP-12 — bare-visibility manifest leaks estate shape, without notice (Low, SPEC/Privacy)

Persona H. A `bare`-visibility publish still emits `manifest.json` (mandatory for custody)
and `cover.json`. The manifest discloses: exact object count, per-object sizes and hashes,
the ordered commit list (hence commit count and, across republishes, cadence), and — since
`obj-cas-imm` ids are stable for unchanged content within a vault's life (`06` §2.3: same
content is *not* deduped across vaults but *is* stable within one) — a diff between two
published manifests reveals **which objects changed and by how much** on each update. For a
"closed but linkable" vault (the investor-pack cover mock in `02` §5), the owner may not
expect that the encrypted site broadcasts "12 objects, 15 KB, updated every Tuesday, last
change touched 2 objects totalling 3 KB." `08` §4 already flags that a docs page *looks* like
an invitation and suggests one line of output; the same reasoning applies to the manifest
itself, which is emitted even at bare.

The `09` beacon analysis (read-time first-party origin) is thorough and I found no gap in it
— the manifest disclosure is a *different* channel (the published artifact, not a runtime
ping) and is not covered by any current invariant (`09` §6 notes readership disclosure "no
current invariant covers — and arguably should").

**Mitigation.** One line in the publish output at `--visibility bare` stating what the
manifest discloses (object count/sizes/commit cadence), so it is a choice. Optionally, a
future `--minimal-manifest` that omits sizes/commit-list for custody-not-needed deployments
— but that breaks keyless custody, so it is a real trade, not a freebie. **Lands in:** `02`
§1 (bare output line), `09` §6 (record the manifest as a second metadata channel). **Gate:
P2/P4, low.**

---

### SP-13 — PBKDF2 is the sole guard for user-chosen passphrases; kdf cache residency (Low, CODE)

Generated keys are strong (§3). But `parse_vault_key`/`derive_read_key`
(`Vault__Crypto.py:123-140`) accept *any* passphrase, and `sgit init` can take a
user-supplied vault key. A human who picks a weak passphrase gets 600k-iteration PBKDF2 as
the only barrier, and for a **published** vault the read-key-derived filenames
(`ref-pid-muw-…` = HMAC(read_key)) and, at public visibility, the read key itself are
exposed — so an offline attacker who suspects a weak passphrase can grind it. 600k iterations
is a reasonable 2026 cost but not a substitute for entropy. Separately, `_pbkdf2_cached` is
an `lru_cache(maxsize=256)` keyed on `(passphrase_bytes, salt)` (`Vault__Crypto.py:26-32`),
so passphrases and derived keys persist in process memory; `clear_kdf_cache` exists
(`Vault__Crypto.py:262`) but I did not find it called on any teardown path.

**Mitigation.** Warn on low-entropy user-supplied passphrases at `init`/`move`; document
that a published vault's security rests on passphrase entropy for user-chosen keys. Confirm
`clear_kdf_cache` is called after sensitive operations (or accept the residency as within
the local-process trust boundary). **Lands in:** out of this pack's scope mostly — note to
the crypto owner. **Gate: later, low.**

---

### SP-14 — No binding between vault_id, key, and content: whole-site forgery is undetectable (Medium, SPEC)

The deepest form of SP-2/SP-3. A reader's *only* trust root is the URL they typed. A host (or
an HTTP MITM) can serve, at that URL, a **completely different vault**: its own
`sgit_public_read_<hex2>` key file, its own manifest, its own ciphertext, all internally
consistent. The reader's loader classifies the key, derives the ref filename, fetches,
decrypts, and renders — attacker content, presented as the publisher's vault. Nothing binds
"this is vault `o7oohxk7` as published by its author" to the bytes. For public vaults this is
"you got the wrong page from a hostile host," which TLS to an honest host mostly prevents;
for a **link shared out of band** (the whole point of "here's my published vault"), a
compromised host substitutes freely.

**Mitigation.** Same as SP-2: a writer-held signing key whose public half is published lets a
reader verify authorship, *if* the reader obtains the public key through a channel other than
the compromised host (in the URL, from `sgit.ai`, from a prior clone). Absent that, be honest
in the docs: **the authenticity of a static-published vault is exactly the authenticity of
the URL and the host serving it; sgit adds confidentiality and (once SP-1 lands) content
integrity, not authenticity.** **Lands in:** rolls into the SP-2 decision and the
non-guarantee note. **Gate: with SP-2.**

---

### SP-15 — vault_id entropy and enumeration (Info)

`vault_id` is 8 chars of lowercase-alphanumeric (~41 bits, `Vault__Sync.py:39`), appears in
URLs, paths, S3 keys, and logs by design (the `VAULT_ID_PATTERN` comment,
`Vault__Crypto.py:21-24`, correctly forbids human-readable ids that would leak *more*). It is
an identifier, not a secret, so 41 bits is fine against guessing a *specific* vault. On a host
that offers directory listing, published vaults are enumerable — but that is inherent to
static hosting and the pack already treats listing availability as a custody feature (`02`
§3). No action; recorded for completeness.

---

## 6. Freshness and rollback — dedicated analysis

The brief asked for real treatment, so here it is consolidated.

**The question:** what binds a reader to *fresh* state? **The answer today: nothing.** This
is not a bug in an invariant; it is a property the invariants do not mention. I1 guarantees
the ciphertext is byte-identical to *some* store; it does not say *the current* store. I3
guarantees a keyless copy is faithful to *what was served*; it does not say *what is true
now*. The manifest records a `head` and `commits`, but is served by the same untrusted
origin and is unsigned.

**The three reader types, and what each can verify at read time:**

| Reader | Has | Can verify content integrity? | Can verify freshness? | Can verify authenticity? |
|---|---|---|---|---|
| CLI with read key | read key | Yes for `obj-cas-imm` **once SP-1 lands** (recompute id); refs/indexes only via GCM tag | **No** — an old valid ref passes every check | **No** — trust root is the URL only |
| Browser loader | key from URL/file/store | Same as CLI, if the Web team implements id checks (REASONED) | **No** | **No** |
| Keyless mirror | nothing | `obj-cas-imm` only, *if* it recomputes ids (SP-3); else trusts manifest | **No** | **No** |

**Attacks this enables (all without breaking any crypto):** freeze (serve yesterday
forever), rollback (serve a specific older coherent snapshot — e.g. pre-advisory, pre-revocation),
partition (serve reader A the real vault and reader B a stale one), and — combined with SP-14
— substitution (serve an entirely different vault at the same URL). On an `http://` target
(SP-6) all four are available to a network MITM with no host compromise.

**Is a fix worth it?** For the public-handbook case the honest answer is "document the
non-guarantee and move on" — the content is public, the host is chosen by the publisher, and
TLS to an honest host closes the network path. For the **private-read and CI tiers**, which
the pack is actively building toward (`11`, decision 14, P9), the trust placed in the host is
higher and the freshness gap is a real, unpriced risk. The recommendation:

1. **Now:** add an explicit non-guarantee to `01` §1 and `02` — "a static host can serve a
   coherent but stale or substituted snapshot; sgit provides confidentiality and content
   integrity, not freshness or authenticity, over a static transport." This is free and it
   is the difference between an accepted risk and an unknown one.
2. **Before private/CI ships:** open a maintainer decision (16) for a **signed, monotonic
   head** using a writer-held key from the existing PKI, public half in `cover.json`. It
   defeats rollback-for-returning-readers and forgery, at the cost of one signature per
   publish and a public-key field. A monotonic counter (TUF's snapshot/timestamp roles,
   collapsed to one signed integer) is the minimum; a signed timestamp/expiry is a cheaper
   partial measure that at least bounds staleness.
3. **Never claimed:** first-view forgery by a host that never served the genuine vault is
   only closable by out-of-band public-key distribution. Say so; don't imply otherwise.

This is the single most important architectural gap in the pack, and it is precisely the
kind of thing that is cheap to design in now and expensive to retrofit after a key format is
in the wild (`00` §7's own warning).

---

## 7. Tier-confusion analysis

The design has **four access tiers** (public read, private read, structure key, vault/write)
and **two transports** (live API, static). Confusions to guard:

- **Key-tier confusion is well handled.** `classify_key` (`Vault__Crypto.py:86`) routes by
  declared prefix; the loader ports it and refuses a `sgit_private_vault_` write key
  (`01` §7, `02` §5). The structure key (`derive_structure_key`, `Vault__Crypto.py:218`)
  decrypts metadata not blobs and is derived one-way from the read key — a clean capability
  reduction. No confusion found here; this part is a strength.
- **Visibility-tier vs access-tier confusion (SP-7).** bare/named/public describe *folder
  contents*, not *who may read*. On a static host, "bare" is not access-controlled — it is
  "key-possession only, unrevocable." The UX must not let bare read as private-in-the-server
  sense.
- **The visibility *downgrade* is handled well.** The fresh-clone-defaults-to-bare hazard
  (R3) that would silently drop the key file on a CI republish is caught by the downgrade
  warning (`02` §1, `05` P4, `11` step 5) and the workflow passes `--visibility` explicitly.
  Good — this was a real footgun and it is closed.
- **Transport-tier confusion (SP-7 again, and SP-2).** The automatic live→static fallback is
  *reported* (good) but silently drops revocation, per-reader auth, read audit, and rate
  limiting, and swaps a freshness-guaranteeing server for a freshness-agnostic folder. A
  reader who thinks "I'm reading vault X" does not necessarily know they dropped from
  "the server vouches for X, now" to "a folder claims to be X." Enumerate the dropped
  properties in one place (`01`).
- **The private-read filename trap is explicitly guarded.** `01` §3 forbids carrying the
  key-in-filename convention from public to private "by analogy," and the classifier keeps
  the word-not-character distinction. Watch that P4's implementation of
  `format_read_key(public=...)` (`Vault__Crypto.py:111`) never emits a `sgit_private_read_`
  file into the surface — `05` P4 asserts exactly this ("`sgit_private_*` can never appear as
  a published filename"). Keep that assertion.

---

## 8. Recommendations mapped to pack files and phases

**Must-fix before the named phase is called done:**

- **SP-1 → P1.** Id-verify every `obj-cas-imm` object on the read/clone path; fail per-object.
  Update `05` P1 acceptance, `03` §2 diagram, add an invariant to `04`.
- **SP-8 → P5 (and P3).** Route manifest `file_id` and virtual serve routes through
  `Vault__Path_Guard`; bound counts/sizes; dedupe. Update `05` P3/P5 acceptance, add a `04`
  traversal cell for mirror.
- **SP-3 → P5.** Mirror recomputes `obj-cas-imm` ids and ignores manifest `sha256` for them;
  rejects conflicting/duplicate entries. Update `01` §4, `05` P5, `04` I3.

**Decision required before the private-read and CI tiers are promoted from tabletop to
supported:**

- **SP-2 / SP-14 → new decision 16 in `06`.** Signed, monotonic head; public key in
  `cover.json`. Until then, the documented non-guarantee (below) is the accepted position.
- **SP-4 → decision 15 / `07`.** CI-config-as-vault-content escalation: least-privilege
  runner, SHA-pinned actions (SP-10), `persist-credentials: false`, no `pull_request_target`,
  and a docs statement that one-repo vault-write grants runner code execution.

**Should-fix in the phase that introduces the surface:**

- **SP-5 → P4 loader / Web team.** Private keys session-memory only.
- **SP-6 → P1 (http warning) + `01` §7 (fragment hygiene, Web team).**
- **SP-7 → P4 / `01`.** Dropped-properties table; bare/named wording.
- **SP-9 → P3.** `Host`-header validation; sharper `--bind` warning.
- **SP-10 → templates / decision 15.** Pin everything the generator emits; fix the committed
  template now so it is not copied as-is.
- **SP-11 → P4b / P4.** CSP mandatory on loader and docs; `connect-src 'self'` as the
  exfiltration backstop.

**Free-and-now (documentation):**

- The freshness/authenticity **non-guarantee** paragraph in `01` §1 and `02` — do this
  regardless of whether decision 16 is adopted. It is the highest value-per-word change in
  the review.
- **SP-12 → `02` §1.** One bare-visibility line on manifest metadata disclosure.

**What blocks what:**

- **P1** is unblocked *except* SP-1 must be part of its definition of done (it is a one-method
  change plus a fixture).
- **P3** is unblocked *except* SP-8 (virtual-route guard) and SP-9 (`Host` check) — both
  small, both stdlib.
- **P2/P4** are unblocked; fold in SP-7 wording and SP-12's line; the visibility-downgrade
  handling is already correct.
- **P5** must not ship without SP-3 and SP-8.
- **P9 and the CI story** should not be promoted to "supported" without the SP-4 least-privilege
  posture and the SP-2 freshness decision, because those are the tiers that place real trust
  in the host and the runner.

---

## 9. Accepted-risk candidates for the maintainer

These are defensible to accept *explicitly*; the ask is a recorded decision, not silence.

1. **Static hosting has no revocation** (SP-7, `06` §2.4). Inherent; the mitigation is
   "publish to object storage and rotate = re-key = new vault," already documented. Accept,
   but make "bare ≠ access-controlled" visible in the UX.
2. **First-view forgery is bounded only by URL/host trust** (SP-14). Inherent to any
   name-resolves-to-bytes system without out-of-band keys. Accept with an honest docs
   statement; do not imply authenticity the design doesn't provide.
3. **Public-vault freshness** (SP-2, public tier only). For a public handbook, a stale
   coherent snapshot is low-harm. Accept for public; do *not* accept for private/CI without
   decision 16.
4. **api-docs=cdn puts jsdelivr on the reader path** (SP-11 residual). SRI + no-referrer +
   pinned version close integrity and correlation; availability and reader-IP-to-CDN remain.
   Already well-analysed in `08`/`09`; accept.
5. **Manifest metadata disclosure at bare** (SP-12). Required for custody; the trade is real.
   Accept with the one-line notice.
6. **CI-config travels with the vault** (SP-4a). The pack "ACCEPTED" this for the desync
   reason; acceptable *only* once the escalation is documented and the runner is
   least-privilege. Not acceptable as an unremarked default.

---

## 10. Note — what a real-GitHub tabletop should additionally probe

The `11` run was simulated hosting and honestly flagged what it could not measure (Pages
propagation, secret masking in Action logs, real-provider ACAO/cache/dot-dir behaviour). From
a security standpoint a real-GitHub run should go further than confirming those rows: it
should *attempt the attacks*. Specifically — verify that `GITHUB_TOKEN` and `SGIT_READ_KEY`
are actually masked in logs when a step echoes a command line (the one channel `11` step 5
could not test); confirm a fork PR carrying a modified `.github/workflows/*.yml` cannot reach
the secret (SP-4, the `pull_request_target` trap); measure whether a private vault's
ciphertext is cacheable/served by Pages at all (dot-dir handling under `.nojekyll` vs
artifact deploy, and whether Pages' `max-age=600` creates an exploitable staleness window,
SP-2); and attempt a manifest with a traversal `file_id` and an over-count against a real
`mirror` once P5 exists (SP-3/SP-8). The most valuable single probe is the freshness one:
publish v2, then serve v1's committed tree from a second origin and confirm — as the design
today implies — that a reader cloning the second origin has *no signal at all* that they are
one revision behind. That negative result, demonstrated on real infrastructure, is what
turns SP-2 from a reviewer's REASONED claim into the decision it deserves to be.
