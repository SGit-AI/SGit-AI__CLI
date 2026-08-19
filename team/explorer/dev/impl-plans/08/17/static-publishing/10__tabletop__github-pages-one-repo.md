# 10 — Tabletop: one GitHub repo carrying the read key, the decrypted files, and the vault

**Date:** 2026-08-19 · **Status:** EXECUTED, not imagined — every `sgit` command below ran
for real against the repo's current code (editable install, Python 3.12 venv) and a real
in-memory SG/Send server (`tests/integration/conftest.py` harness). Only two things are
simulated, and they are marked every time they appear:

| Simulated | Stand-in | Why |
|---|---|---|
| `sgit publish` (P2, not built) | `simulate_publish.py` — assembles the folder per `07` §2; **key derivation, ref decryption, and the commit parent-walk use sgit's real crypto classes** | the command doesn't exist yet |
| GitHub + Pages | local bare git repo + `python3 -m http.server` | can't create throwaway GitHub repos from here |

Everything else — `init`, `commit`, `push`, `derive-keys`, key classification, the
read-only static clone, decryption, verification — is the shipped CLI/library code.

> **Correction (r10):** step 2's `.gitignore` — only `.sg_vault/local/` — is
> **insufficient**: one keyed `sgit vault backup` plus `git add -A` would commit the vault
> key inside the backup zip. The canonical set is `local/` + `backups/` + `.sg_vault_new/`
> (`07` §4). Also r10 removed the publish folder's `*` self-ignore, so step 4's
> `git add -f` is no longer needed — plain `git add -A` includes the surface. Findings
> F1–F4 unaffected.

> **Spec change after this run (r9, `CHANGELOG.md`):** steps 3–5 executed the then-current
> spec, in which publish **copied** the store into
> `.sg_vault/publish/api/vault/read/<vid>/bare/**`. The maintainer then removed that copy:
> publish now emits the plaintext surface only, and the store is composed in at deployment.
> Step 4's git-dedup measurement therefore becomes moot (nothing left to dedupe), and mode B
> — clone straight off the repo's own `.sg_vault/`, which this run **verified with zero
> projection involved** — is exactly the shape the r9 spec generalises. The findings
> (F1–F4, C1–C7) are unaffected.

**Scenario** (the maintainer's): one repo, served by GitHub Pages, containing **all three**
at once: the public read key, the decrypted (hydrated) files, and the encrypted vault store
with its history.

---

## Step 0 — the cast

| Party | Has | Wants |
|---|---|---|
| **Author** (agent) | the vault key | to publish the handbook so anyone can browse or clone it |
| **GitHub** | the repo | — (it can read nothing; it stores ciphertext + deliberately-public plaintext) |
| **Reader** | the URL only | browse the site; clone the vault with the key found on it |
| **Archivist** | the URL only, refuses keys | a verifiable backup they cannot read |
| **CI runner** | a fresh `git clone` | republish on every push |

## Step 1 — author creates content and the vault (REAL)

```console
$ mkdir acme-handbook && cd acme-handbook
$ cat > index.html         # the vault's OWN site page — this is content, not the loader
$ mkdir docs && … onboarding.md, security.md, logo.png

$ sgit init --existing .
Vault created!  Vault ID: o7oohxk7
  Vault key: sgit_private_vault_nv02px0pjg7xwhkhnj7ytiqm:o7oohxk7
$ sgit commit "handbook v1"
$ sgit push .
Push complete. Named branch updated.
  Pushed 1 commit(s), 4 object(s) uploaded.
  commit obj-cas-imm-36a798c37abe
```

**Author's local folder now** (real listing):

```
acme-handbook/
├── index.html  docs/{onboarding.md, security.md, logo.png}     PLAINTEXT (hydrated)
└── .sg_vault/
    ├── bare/data/obj-cas-imm-{9 objects}                        CIPHERTEXT
    ├── bare/indexes/idx-pid-muw-dd6887115f9d                    CIPHERTEXT
    ├── bare/keys/key-rnd-imm-{3}                                CIPHERTEXT (PKI)
    ├── bare/refs/ref-pid-muw-fb98b8b3444b  ref-pid-snw-…        CIPHERTEXT (mutable)
    └── local/{vault_key, token, base_url, config.json, *.pem}   SECRETS — never leaves
```

```console
$ sgit vault derive-keys sgit_private_vault_nv02px0pjg7xwhkhnj7ytiqm:o7oohxk7
read_key:  8c110fa35775c8c6f153d6c1242dfc875330a40f0c59c57708b19e6f89d382ad
ref_file_id: ref-pid-muw-fb98b8b3444b        ← matches the file on disk: HMAC(read_key)
```

## Step 2 — git on top of the vault (REAL)

```console
$ git init -b main
$ printf '.sg_vault/local/\n' > .gitignore          # ONLY the secrets are git-ignored
$ git add -A && git commit -m "handbook v1 (plaintext + encrypted vault store)"
```

**GitHub repo (after Step 4's push) — `git ls-files`:**

```
.gitignore
.sg_vault/bare/data/obj-cas-imm-…   (all of bare/: data, indexes, keys, refs)
docs/logo.png  docs/onboarding.md  docs/security.md
index.html
```

Both systems ignore each other's private half, mechanically: `.git` is in sgit's
`ALWAYS_IGNORED_DIRS`; `.sg_vault/local/` is in `.gitignore`. The repo carries the
hydrated plaintext **and** the ciphertext store with its full history.

> **Live finding (F1):** `sgit status` immediately showed `+ .gitignore` — the root
> `.gitignore` is itself **vault content** and travels into every clone of the vault.
> Harmless here, but it means the vault is not entirely ignorant of the git layer, and a
> vault cloned elsewhere arrives with the publisher's ignore rules. Documented, not fixed.

> **Live finding (F2):** a *refused* `sgit push` (uncommitted changes) still **rewrote the
> mutable ref bytes** — same commit id, fresh IV — leaving `git status` showing
> ` M .sg_vault/bare/refs/ref-pid-muw-…` with no real change. In this pattern that produces
> spurious dirty states and noise commits. Filed as a code issue in the v1 review (§F2).

## Step 3 — publish (SIMULATED assembly; real crypto inside)

```console
$ sgit publish --visibility public                   # SIMULATED (P2)
Publishing vault o7oohxk7 -> .sg_vault/publish/
  Ciphertext objects   18
  Commits (head first) [ea6abfe5d5ea, 36a798c37abe, e198658f3e4a]   ← REAL parent walk,
  Plaintext surface    4 + manifest                                    read key only
  Visibility           public
```

What the real crypto proved while assembling:

- the ordered commit list required **only the read key** (`import_read_key` → ref decrypt →
  `Vault__Commit.load_commit` → parents). **`sgit publish` never needs the vault key.**
- ciphertext copies are `shutil.copy2` — byte-identical to the store (I1 by construction).

**Author's folder gains exactly one subtree** (I6 check below):

```
.sg_vault/publish/
├── .gitignore                          "*"          (07 §4 — self-ignoring)
├── index.html                          the LOADER (placeholder for the bundled template)
├── cover.json  manifest.json
├── sgit_public_read_8c110fa35…d382ad   the key, as a filename (public visibility)
└── api/vault/read/o7oohxk7/bare/**     18 files, byte-identical to .sg_vault/bare/**
```

**Invariant I6, checked with the real CLI:**

```console
$ sgit push .
Nothing to push — vault is already up to date.        # bare/data: 12 objects -> 12
```

Publish → push is a no-op. The amplification loop is impossible by construction.

## Step 4 — commit the publish folder and push to GitHub (REAL git)

The folder self-ignores (`.gitignore` = `*`), so committing it is an **explicit** act:

```console
$ git add -A                     # plaintext + bare store
$ git add -f .sg_vault/publish/  # -f overrides the self-ignore — deliberate, visible
$ git commit -m "publish: loader + manifest + public read key + ciphertext projection"
$ git push origin main
```

**Measured — the double-commit is nearly free.** Because the projection is byte-identical
to the store (I1), git content-addressing dedupes every ciphertext copy:

```
files in HEAD tree: 46    unique git blobs: 29    deduped: 17
blob 5031a93ca8de : .sg_vault/bare/data/obj-cas-imm-05e6c5d1f366
                 == .sg_vault/publish/api/vault/read/o7oohxk7/bare/data/obj-cas-imm-05e6c5d1f366
```

All 17 projection copies share blobs with the store. The repo pays only tree entries plus
the genuinely new plaintext files. (Corollary: `--api-docs=bundled` would add its 1.53 MB
once; `--bundles` zips would **not** dedupe — zip containers differ from loose bytes — so
skip bundles on git-hosted targets. The git protocol is already the bundle.)

**The GitHub repo now contains all three things the scenario asked for:**

| What | Where in the repo | State |
|---|---|---|
| decrypted files | `index.html`, `docs/**` | plaintext (the work tree is the hydration) |
| the vault + history | `.sg_vault/bare/**` (+ git history of it) | ciphertext |
| the read key | `.sg_vault/publish/sgit_public_read_<64hex>` | plaintext filename, deliberate |

## Step 5 — Pages deployment (SIMULATED hosting; two real modes)

### Mode A — Actions artifact (recommended): the publish folder IS the site root

```yaml
# .github/workflows/pages.yml — lives in the REPO, not the vault (16 Aug brief, item 4)
- uses: actions/checkout@v4                                  # pin by SHA in real life
- uses: actions/upload-pages-artifact@v3
  with: { path: .sg_vault/publish }
- uses: actions/deploy-pages@v4
```

**What Pages serves (real listing of the deployed root):**

```
/index.html                 ← the loader
/cover.json  /manifest.json
/sgit_public_read_8c110fa35…
/api/vault/read/o7oohxk7/bare/{data,indexes,keys,refs}/…
```

No Jekyll pass, no dot-dir problem, and the repo layout is invisible to readers.

### Mode B — classic branch-root deploy: the whole repo is the site

```
/index.html  /docs/**                      ← the DECRYPTED files, browseable directly
/.sg_vault/bare/**                         ← the store, fetchable
/.sg_vault/publish/**                      ← loader + manifest + key
```

**Caveat that bites (F3):** Pages' default Jekyll pass **excludes dot-directories** —
everything under `.sg_vault/` would silently not be served. Branch-root deploys need a
`.nojekyll` file at the repo root. That file is *deployer* configuration: it belongs in the
repo (committed next to the workflow), never in `sgit publish` output (I1).

## Step 6 — the reader clones back over plain GETs (REAL, both modes)

```console
$ python reader_clone.py http://127.0.0.1:8431/modeA o7oohxk7 sgit_public_read_8c110fa…
key classified as : Enum__Key_Kind.READ_PUBLIC          ← real classify_key (67c2ab6)
layout sniffed    : api/vault/read/{vid}/{fid}
  file: .gitignore  index.html  docs/logo.png  docs/onboarding.md  docs/security.md

$ python reader_clone.py http://127.0.0.1:8431/modeB/.sg_vault o7oohxk7 sgit_public_read_…
layout sniffed    : {fid}                               ← flat layout, same transport
$ diff -r --exclude=.sg_vault --exclude=.git author-tree/ reader-clone/
IDENTICAL
```

> **Live finding (F4) — the repo is already a static vault.** Mode B's clone ran against
> `…/repo/.sg_vault` with **no publish step involved at all**: the committed bare store is
> flat-layout clonable today, by shipped code. What `sgit publish` adds is not clonability —
> it is the **browser** (loader), **custody** (manifest), and **key discovery** (the
> filename). Readers of this doc should not conclude publish is optional: without the
> manifest there is no keyless mirror, and without the key file there is no in-page open.

## Step 7 — custody without access (REAL, keyless)

```console
$ curl …/modeA/manifest.json                       # the ONLY way to learn filenames keyless
$ for each manifest.objects[]: curl -O …           # 18 objects
mirrored 18 objects; content-addressed verified: 12 ok, 0 bad — ZERO key material used
```

The 12 `obj-cas-imm-*` objects verify as `sha256(ciphertext)[:12] == id` with no key and no
trust in the host. (Refs/indexes/keys are `pid`/`rnd`-named — HMAC-derived, not
content-addressed — so custody verifies them only by presence; noted in the v1 review, §R6.)

## Step 8 — the update cycle (REAL end to end)

```console
$ echo "Day 3: clone the handbook vault yourself…" >> docs/onboarding.md
$ sgit commit && sgit push .            #  Pushed 1 commit(s) — obj-cas-imm-236f178f62d2
$ sgit publish --visibility public      #  SIMULATED — commits now [236f…, ea6a…, 36a7…, e198…]
$ git add -A && git add -f .sg_vault/publish/ && git commit && git push
→ Pages redeploys (workflow)
$ fresh reader clone …
Day 3: clone the handbook vault yourself: sgit clone <key on the site>.   ✔
```

Two timing notes for the deployer table: Pages serves everything with `max-age=600`, so a
reader can see the **old head ref** for up to ~10 minutes after a redeploy (immutable
objects are unaffected — ids change when content does). And the loose-object GET fan-out is
exactly the measured economics of `06` §2.6 — request count, not bytes.

## Step 9 — the CI runner drill (REAL, and it fails first)

```console
$ git clone github/acme-handbook.git ci-runner && ls ci-runner/.sg_vault
bare  publish                                   ← local/ ABSENT — it was git-ignored
$ sgit publish             # SIMULATED
FileNotFoundError: …/.sg_vault/local/vault_key
```

A fresh checkout has **no key material** — correct, and it means CI cannot publish out of
the box. The recovery is already sitting in the repo:

```console
$ python ci_publish_readkey.py ci-runner        # derives from the COMMITTED key filename
CI publish with READ KEY ONLY: head=obj-cas-imm-ea6abfe5d5ea  commits=3  vault_key needed: NO
```

So the workflow for a **public** vault needs no secrets at all: the committed
`sgit_public_read_*` filename is sufficient for a full republish. For a private (`bare`)
vault, CI needs the read key as a repository secret — and must pass `--visibility`
**explicitly**, because a fresh clone's visibility defaults to `bare` (decision 5): a CI
republish that forgets the flag silently drops the key file and breaks the site (safe
direction, but broken). Both belong in the canonical workflow file. (Review §R2, §R3.)

## Step 10 — what each party ends up holding

| | plaintext files | ciphertext + history | read key | vault (write) key | can read | can write |
|---|---|---|---|---|---|---|
| Author | ✔ work tree | ✔ `.sg_vault/bare` | ✔ derived | ✔ `local/` | ✔ | ✔ |
| GitHub / Pages | ✔ (deliberately) | ✔ | ✔ (deliberately) | ✘ | ✔ *because visibility=public* | ✘ |
| Reader | ✔ (cloned) | fetched, discarded | ✔ (from the site) | ✘ | ✔ | ✘ |
| Archivist | ✘ | ✔ mirrored + verified | ✘ | ✘ | ✘ | ✘ |
| CI runner | ✔ (checkout) | ✔ | ✔ (committed file) | ✘ | ✔ | ✘ |

The one deliberate act that made GitHub able to read: `--visibility public` publishing the
key. At `bare` visibility the same repo layout works and GitHub holds ciphertext plus the
work-tree plaintext the author *chose* to commit — which, in this one-folder pattern, is
already the author's decision the moment they `git add` the work tree, before sgit
publishing enters the picture at all.

---

## Reproduce

Lab scripts — promoted to `scripts/tabletop__static_publishing/`:
`simulate_publish.py` (the P2 stand-in), `reader_clone.py`, `ci_publish_readkey.py`,
`run_server.py`. Real components used: `sgit init/commit/push/vault derive-keys`,
`Vault__Crypto` (derive/import/classify), `Vault__Ref_Manager.read_ref`,
`Vault__Commit.load_commit`, `Vault__Sync.clone_read_only`,
`scripts/spike__static_vault_transport.py`, `tests/integration/conftest.py` server.

Findings F1–F4 and the spec gaps they expose are consolidated in
`team/explorer/architect/reviews/08/19/v1__review__static-publishing-full-pass.md`.
