# Response — v0.33.59 "Source And Output Are Being Conflated"

**Date:** 2026-08-19 · **From:** sgit CLI team (architect) · **To:** project lead
**Re:** `v0.33.59__crossteambrief__staticpublishingfeedback…` (16 Aug)
**Pack under review:** `team/explorer/dev/impl-plans/08/17/static-publishing/`

**Five of six accepted, one changed.** Item 5 — copying default page assets into the vault at
setup — **breaks the invariant it is written to protect**, and contradicts the brief's own
third principle. The fix is one word: the folder starts **empty**. Everything else in the
brief is right, and two items are sharper than what the pack had.

---

## Verdict

| # | Brief's item | Verdict |
|---|---|---|
| 1 | Move published page/scripts/styles/manifest out of the repo root | **Accepted — half already done, from the other direction** (§1) |
| 2 | Rename the folder to something reserved | **Accepted** — `.sgit/publish/`, with one caveat (§5) |
| 3 | Merge rule replaces the index special case | **Accepted, with a gate added** — the rule resolves *which source wins*; it must not decide *what may be plaintext* (§3) |
| 4 | Pipeline definitions in the repository, not the vault | **Accepted — and it fixes a latent disclosure bug in our decision 5** (§4) |
| 5 | Generate the folder's default contents from a canonical source | **Changed.** Copy-at-setup produces exactly the drift it is meant to prevent (§2) |
| 6 | Deterministic transformation, runnable locally | **Accepted — already specified**, plus one precision about `generated_by` (§6) |

## 1. Item 1 — same defect, found from both ends; one half is already fixed

The brief reads the pack's published layout (`01` §3) as a proposal to write plaintext at the
**repository root**. That was a fair reading of the pack as it stood on 16 August: every
mockup said `sgit publish ./site`, run from inside the work tree, with no rule forbidding it.

On 18 August the same defect was raised independently — *"I don't think this should be
allowed… since all those files would be marked to be added to the sgit vault"* — and the
answer is now `07__publish-target.md`: the output directory **may not be inside the work
tree, nor contain it**, checked on `realpath` before any byte is written, with
`.sg_vault/publish/` as the no-argument default. The failure is worse than untidiness: a
published folder inside the work tree is ordinary content to `sgit push`, so publish → push →
publish **doubles the store on every cycle**, silently.

**But that is only the output half.** The brief is also asking for something the pack does not
have: a **committed source folder in the vault** holding the page and its assets, consumed by
the transformation. Source in, output out. That half is accepted, subject to §2 and §3.

So the shape becomes:

```
work tree/
├── .git/                      ignored by the vault (ALWAYS_IGNORED_DIRS)
├── .sg_vault/                 the store — local/ gitignored, bare/ committed
│   └── publish/               DEFAULT OUTPUT — derived, self-ignoring (§5)
├── .sgit/publish/             SOURCE — tracked, empty unless overriding (§2)
└── … the vault's actual files
```

## 2. Item 5 is the one to change — copy-at-setup *is* the drift

The brief names the tension exactly right: a per-vault folder of page assets will drift, the
byte-identical-loader invariant dies, and *"nobody notices because nothing breaks visibly"*.
Its proposed resolution is copy-from-canonical at setup, refresh on demand, override by the
merge rule. **That resolution does not hold**, for three reasons that compound:

1. **A copy is a snapshot, not a binding.** The moment `index.html` is committed it is vault
   content. Nothing distinguishes "the pristine v0.15.6 template" from "the template with one
   character changed" — there is no provenance record and no comparison step.
2. **Drift arrives without anyone editing anything.** A vault set up in August carries the
   August loader; one set up in November carries November's. They differ. That is the
   invariant gone, purely from time, with zero user error.
3. **The merge rule makes it permanent.** "Never overwrite what is already there" means that
   once a stale copy exists, publish prefers it over the current bundled template **forever**.
   Copy-at-setup plus never-overwrite pins every vault to its setup-day loader.

It also contradicts the brief's own **third principle**. A vault carrying a folder of
publishing scaffolding *is* a vault that knows it is published — the folder is right there in
every clone, and it grows with each asset publishing needs, which is precisely consequence
two of the conflation the brief is correcting.

### The one-word fix: the folder starts empty

Do not materialise defaults. Publish merges **bundled template → output**, then **vault
override folder → output, never overwriting** — the brief's rule exactly, but the left-hand
side is sgit's template rather than a copy of it:

| | Copy defaults in at setup | **Folder empty unless overriding** |
|---|---|---|
| vault with no override | carries N files it never uses | **has no folder at all** |
| loader across such vaults | drifts by setup date | **byte-identical, and stays so across sgit versions** |
| a deliberate override | works | works, identically |
| "does the vault know it is published?" | yes | **no** |
| refresh to a new loader | manual, per vault, never done | automatic — next publish uses the shipped template |

`sgit vault loader --eject` writes the current template into `.sgit/publish/` for someone who
wants to start from it — an explicit act, at the moment of overriding, not at setup. And
invariant I4 sharpens into something assertable: **byte-identical across all vaults that do
not override**, with the manifest recording which files came from the template and which from
the vault, so "did this vault override the loader?" is answered by inspection.

## 3. The merge rule is right — and it needs a gate beside it

Accepted, including both properties the brief attaches: **report what was skipped**, and **no
force flag** (a flag to overwrite would eventually be used by accident on the one vault that
needed its own page — the same reasoning as our `--with-plaintext` refusal).

One thing must not be lost in the swap. The pack's plaintext surface is a **fixed allow-list
in code**, for a specific reason (`01` §5): if the surface were decided by matching vault
content, *anyone who can write to the vault* — a collaborator, a compromised agent — could
move a file into the plaintext surface by naming it. A merge rule that emits whatever is in
the folder reopens exactly that: drop `notes.txt` into `.sgit/publish/` and it is published in
the clear, from a vault whose key is not published.

The two mechanisms have different jobs and both survive:

> **The allow-list decides what may be plaintext. The merge rule decides which source wins.**

Concretely: an override is honoured only if its path is on the allow-list — `index.html`,
`cover.json`, and typed assets under `.sgit/publish/assets/` (`.css .js .svg .png .woff2`).
Anything else in the folder is **reported and skipped**, never emitted. `ALWAYS_IGNORED_FILES`
still applies (no `.env`, no keys), `sgit_private_*` can never be a published filename, and
every emitted file is recorded with its `sha256` in the manifest — so the brief's
"report what it skipped" extends to "report what it took from the vault", and the audit is in
the artefact rather than in the console history.

## 4. Item 4 is right, and it fixes a bug we had shipped into the plan

Agreed without reservation: pipeline definitions, deployment targets and credentials belong to
the repository, not the vault; a clone must not carry somebody else's deployment settings.

**It also invalidates our decision 5.** The pack recorded visibility *in the vault*, reasoning
that "a visibility default that drifts is a disclosure, not a preference". Under the brief's
third principle, visibility is configuration, not content — and following the principle turns
out to be the *safer* option, not merely the tidier one:

> If `visibility: public` travels inside the vault, then whoever clones it and runs `sgit
> publish` **publishes the read key by inheritance** — a disclosure caused by config the
> cloner never chose.

So visibility moves to `.sg_vault/local/config.json` (already per-clone, already untracked,
already exists), an unconfigured clone defaults to **`bare`**, and the anti-drift requirement
is met by *recording per clone* rather than by travelling with the vault. Decision 5 flips.

## 5. Item 2 — the name, and one interaction with the working pattern

The collision is real and the precedent cited (14 August, "plugins") is the right one.
Recommendation: **`.sgit/publish/`** — one reserved top-level namespace for tracked,
sgit-aware content, with room for later needs so we do not claim another generic name each
time. Dotted names are **tracked by default** in sgit (`Vault__Ignore` ignores dotfiles only
by explicit set membership), which is what an override folder needs.

The caveat worth stating: `.sgit/` and `.sg_vault/` are similar names with **opposite**
tracking semantics — one is tracked content, the other is never-tracked machinery. If that is
judged too close, `.sgit-publish/` is unambiguous at the cost of a future land-grab.

**And one thing the brief's working pattern changes about our default.** In the described
arrangement the git repo carries `.sg_vault/bare/` (ciphertext, committed) and gitignores only
`.sg_vault/local/` (the key). Our new default output — `.sg_vault/publish/` — would therefore
land **inside git's view**, committing a second copy of every object, plus up to 1.53 MB of
Swagger UI, into history. Fix: `sgit publish` writes a `.gitignore` containing `*` **inside**
`.sg_vault/publish/`, so the folder ignores itself without touching the user's `.gitignore`.
Self-contained, no surprise edits to a file the user owns.

Worth recording as an observation: in that pattern the repository is **already ~90% of a
published vault** — it carries the ciphertext store and its history. What publishing adds is
the plaintext surface and the API-path layout, and our transport already sniffs the flat
layout. That is a strong argument for the brief's instruction not to disturb the arrangement.

## 6. Determinism — agreed, and already required

`P2` acceptance already says *"publishing the same vault twice produces identical bytes"*, and
I1 asserts destination-independence. "Runnable locally with the same output as the pipeline"
is added explicitly.

One precision, so the claim is testable rather than aspirational: `manifest.json` carries
`generated_by: "sgit v0.15.6"`, and `cover.json` carries `updated`. Determinism therefore
holds as **same vault + same sgit version → identical bytes**, and the *ciphertext* subtree is
deterministic without qualification. Nothing else timestamped, randomised or
environment-dependent may enter the output — and the test asserts the stronger ciphertext form
directly, so a stray timestamp fails the suite rather than being argued about.

## 7. Item 6 — the interface description

Agreed, and already specified: `08__api-docs.md` requires `api/openapi.json` to be **generated
from `manifest.json`**, never handwritten, precisely because a hand-maintained description
drifts from what is served. The brief's *"could come from another static place, but we could
control those options there"* is answered in `09__asset-origin.md`: a first-party asset origin
is right at **publish time** and wrong at **read time**, because a read-time origin makes us
the beacon every vault reader pings.

The brief's closing observation is the useful one — the loader, the spec and the docs page are
the same shape: *a standard artefact, generated from a canonical definition, overridable if a
vault genuinely needs its own*. §2 and §3 above are how that shape is made safe.

## 8. What changes in the pack

1. `01__architecture.md` — add the source/output split, `.sgit/publish/`, and the merge rule
   beside the allow-list, with §3's division stated as the rule.
2. `01` §5 / decision 2 — "the loader is always sgit's template" becomes "always sgit's
   template **unless the vault deliberately overrides it**, and the override is declared".
3. `06` decision 5 — **flips**: visibility moves out of the vault to per-clone local config,
   defaulting to `bare`.
4. `06` — new decisions: the override-folder name, and empty-vs-populated (§2).
5. `07__publish-target.md` — `.sg_vault/publish/` emits a self-ignoring `.gitignore`.
6. `04` — I4 restated as "identical across all non-overriding vaults", asserted from the
   manifest's per-file provenance.
7. `05` — P2 gains the merge rule and the allow-list gate; P4 loses the in-vault visibility
   record.

**Open for the project lead:** §2 is the only place this response departs from the brief. If
copy-at-setup is preferred anyway, say so and it will be built that way — but the
byte-identical-loader invariant should then be **withdrawn** rather than left in the pack,
because it will not survive contact with the first refresh nobody runs.
