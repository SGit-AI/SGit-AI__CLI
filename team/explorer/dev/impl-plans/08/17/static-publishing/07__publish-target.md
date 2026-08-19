# 07 — The publish output

**Revised:** 2026-08-19. The first version of this file was a rule policing *where* an output
directory may live. The maintainer removed the question instead:

> *"the `.sg_vault/publish` should be the only folder that changes after an `sgit publish`
> command has been executed… this should contain the required details and content for
> publishing in multiple places (GitHub Pages, Local, netlify, S3 bucket, etc…), in a way this
> `.sg_vault/publish` doesn't care where it is published."*

**`sgit publish` takes no target.** It writes one folder, `.sg_vault/publish/`, and nothing
else on disk changes. Deployment is a separate act, performed by whatever puts files on a
host.

---

## 1. What this deletes

The previous version of this file existed to police an output-directory argument. With no
argument there is no question to police, and five things go away at once:

| Was needed | Now |
|---|---|
| containment rule, computed on `realpath` in both directions | **gone** — there is one path, and it is fixed |
| the `--force`-on-an-ancestor disaster (clearing a parent dir would delete `.sg_vault`) | **gone** — nothing outside the folder is ever written or cleared |
| the amplification loop (publish → push → publish doubles the store) | **gone by construction** — `.sg_vault` is in `ALWAYS_IGNORED_DIRS` in every shipped version |
| the "already ignored by `.gitignore`" escape hatch, and its refusal messages | **gone** — no escape hatch is needed from a rule that no longer exists |
| a `.site` / `.sgit/publish/` naming decision | **gone** — no new tracked folder is introduced, so nothing can collide with vault content |

The evidence that motivated the rule still stands and is why the fixed path is the right one:
`sgit push` skips only what `Vault__Ignore` declares (`Vault__Sync__Push.py:765-773`), so any
published folder *outside* `.sg_vault/` would be ordinary content, and publish → push →
publish would double the store on every cycle, silently.

## 2. The output is a finished, target-agnostic artefact

```
.sg_vault/publish/
├── .gitignore                              containing `*` — see §4
├── index.html                              PLAINTEXT  loader (resolved — see §3)
├── cover.json                              PLAINTEXT
├── manifest.json                           PLAINTEXT  objects, commits, plaintext surface
├── sgit_public_read_<64-hex>               PLAINTEXT  only when visibility is public
├── api/openapi.json                        PLAINTEXT  optional (`08`)
├── api/docs/                               PLAINTEXT  optional (`08`)
├── api/vault/read/<vault_id>/bare/…        CIPHERTEXT byte-identical to the store
└── bundles/                                optional (`P6`)
```

**Nothing target-specific goes in it.** No `CNAME`, no `.nojekyll`, no `netlify.toml`, no
`_headers`, no bucket policy, no cache-control metadata. Those are decisions of the place it
lands, and putting any of them here would break invariant I1 — that the published bytes are
identical regardless of destination — which is the property that makes one folder deployable
to four hosts.

That also means a deployer can be **dumb**: `rsync -a`, `aws s3 sync`, `git add`, or a static
server pointed straight at the folder. Nothing needs to interpret the contents.

## 3. Overrides: the vault's own root files win, resolved at publish time

The convention, from the 16 August brief and confirmed by the maintainer:

> **A file at the root of the vault overrides the default of the same name in the output.**
> Copy, never overwrite, and report what was skipped.

So a vault containing `index.html` gets *its* `index.html` as the published page; a vault
without one gets sgit's bundled loader. This is the whole override mechanism — **no source
folder, no scaffolding committed to the vault, nothing copied in at setup.** A vault that
overrides nothing carries nothing extra, so the brief's third principle ("the vault does not
know it is published") holds literally rather than approximately.

It also disposes of the drift problem for free: nothing is ever *copied* into a vault, so no
vault can be pinned to a stale loader. `sgit vault loader --eject` writes the current template
into the vault root for someone who wants to start from it — an explicit act at the moment of
overriding, never at setup.

**Resolve it in `sgit publish`, not in the deployer.** The folder must be *finished* when
publish returns, or every deployer — the Action, the Netlify build, the S3 script, `sgit vault
serve` — reimplements the merge and they diverge. Deployer discretion belongs to genuine
target decisions (§5), not to what the artefact contains.

**Two properties to keep with it:**

- **Report what was taken.** A vault override is printed at publish time *and* recorded in
  `manifest.json` with its `sha256`, so the audit lives in the artefact rather than in console
  history.
- **No force flag.** A flag to overwrite an override would eventually be used by accident on
  the one vault that needed its own page — the same reasoning as the `--with-plaintext`
  refusal.

**The one cost, stated plainly:** a vault whose *subject* is a website legitimately has a root
`index.html`, and publishing will emit it as plaintext — including at `--visibility bare`,
where the vault's key is not published. That is the naming collision the 16 August brief
warned about, relocated rather than removed. It is acceptable because the surface is a **fixed
allow-list of names in code** (`index.html`, `cover.json`) rather than a folder whose contents
are emitted wholesale — a collaborator cannot widen the plaintext surface by adding files —
and because publish says so, loudly, every time:

```console
  Loader        ./index.html from the vault (overrides the bundled template)
                ⚠ published as PLAINTEXT, and this vault's key is not published
```

## 4. The folder ignores itself

`.sg_vault/publish/` contains a `.gitignore` whose entire content is `*`.

This matters because of the working pattern the brief describes: a git repo on top of a vault,
committing `.sg_vault/bare/` (all ciphertext) and gitignoring only `.sg_vault/local/` (which
holds the key). In that arrangement `.sg_vault/publish/` is inside git's view, so without this
the output — a second copy of every object, plus up to 1.53 MB of Swagger UI — lands in git
history.

A nested `.gitignore` is the right instrument precisely because it keeps rule 2 true: **the
only file publish writes outside the folder is none.** Editing the user's root `.gitignore`
would break that.

## 5. What the deployer owns

sgit produces the folder and documents the conventions. A publishing target honours as many as
it wants — the artefact works either way.

| Decision | Owner | Note |
|---|---|---|
| where the folder lands (repo subdir, bucket prefix, docroot) | deployer | the layout is relative throughout; `api/openapi.json` uses `servers: ["."]` for this reason |
| `CNAME`, `.nojekyll`, `_headers`, `netlify.toml`, bucket policy | deployer | target-specific by definition |
| cache-control (long for `bare/data`, short for `bare/refs`) | deployer | immutable vs mutable is documented in `01` §3; only the host can act on it |
| CORS headers | deployer | GitHub Pages already sends `access-control-allow-origin: *` (measured) |
| swapping the bundled loader for a hosted app on a CDN origin | deployer | fine as an **explicit** choice; the folder must stay self-sufficient without it, or the "no server needed" claim stops being true — and a hosted origin sees every reader (`09`) |

## 6. Acceptance criteria (P2)

- [ ] `sgit publish` takes **no output-directory argument**.
- [ ] After a publish, **the only path that changed is `.sg_vault/publish/`** — assert with a
      full work-tree hash before and after, not by inspection of the code.
- [ ] `sgit push` immediately after a publish adds **zero** objects and leaves the head
      unchanged (invariant I6).
- [ ] `.sg_vault/publish/.gitignore` exists and contains `*`; the user's root `.gitignore` is
      **byte-unchanged**.
- [ ] A vault with a root `index.html` publishes that file; a vault without one publishes the
      bundled template; both are recorded in `manifest.json` with hashes and a provenance
      field.
- [ ] The override is reported on stdout, and the plaintext warning appears when visibility is
      not `public`.
- [ ] No target-specific file appears in the output — assert the emitted set against the
      allow-list, so a future `CNAME` needs a decision rather than a commit.
- [ ] Publishing twice produces byte-identical output (with `08`'s `generated_by` caveat).

## 7. Knock-on

- **`sgit vault serve`** takes no argument either in the common case: it serves
  `.sg_vault/publish/`, publishing first if the folder is absent or stale.
- **Deployment is out of the CLI's scope for now.** `rsync`, `aws s3 sync`, a GitHub Action, or
  a static host pointed at the folder. If a `sgit publish --copy-to <dir>` is ever wanted it is
  a *pure copy* of a finished folder, and can carry a one-line guard (refuse a destination
  inside the work tree) rather than the ruleset this file used to contain.
