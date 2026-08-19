# Change control — static-publishing pack

Newest first. **Every commit that edits a spec file in this pack adds an entry here** —
what changed, *why* (the trigger), and which decisions moved. A reader returning after a
gap reads this file first; a developer agent's definition of done includes updating it
(`00` §4). The pack has reversed load-bearing decisions more than once — that is healthy,
but only if the reversals are legible in one place.

Conventions: **decisions** reference the numbered table in `06` §1; **R-numbers** are
findings from the 19 Aug review (`team/explorer/architect/reviews/08/19/v1__…`); **F-numbers**
are live findings from the executed tabletop (`10`).

---

## 2026-08-19 — r8: consistency pass + change control (this entry's commit)

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
