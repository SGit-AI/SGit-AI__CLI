# 02 — Commands & UX

Every block below is the **intended user-facing output**. Match the wording, or explain the
change in the PR — several of these strings are load-bearing (they are the only place a
user learns why an irreversible thing is irreversible).

---

## 1. `sgit publish`

```
sgit publish [--visibility bare|named|public] [--with-plaintext]
             [--bundles] [--layout api-path|flat] [--force]
             [--api-spec] [--api-docs[=cdn|bundled]]
```

**There is no output-directory argument.** `sgit publish` writes exactly one folder,
`.sg_vault/publish/`, and nothing else on disk changes; deployment is a separate act performed
by whatever puts files on a host. See [`07__publish-target.md`](07__publish-target.md).

### Baseline — private, ciphertext only (the safe default)

```console
$ sgit publish
Publishing vault q7r6d5zd → .sg_vault/publish/

  Ciphertext objects   13  (15 KB)      api/vault/read/q7r6d5zd/bare/…
  Plaintext surface     3               index.html, cover.json, manifest.json
  Visibility           bare             no key published — readers supply their own

Published. Next:
  sgit vault serve               — browse it locally (a local folder cannot be opened directly)
  sgit clone <read-key>:q7r6d5zd — clone it back from any GET host
```

### Public — the consequence is stated, not implied

```console
$ sgit publish --visibility public

  ⚠ This publishes the READ KEY alongside the vault.
    Anyone with the URL can read every file in it, now and in every future
    publish of this content. This cannot be undone: copies cannot be recalled.
    Continue? [y/N] y

  Ciphertext objects   13  (15 KB)
  Plaintext surface     4               + sgit_public_read_c28b118c…
  Visibility           public           key published in the folder

Published.
```

### Invariant 5, enforced — refuses, and says why

```console
$ sgit publish --with-plaintext
error: --with-plaintext requires --visibility public.

  Expanded plaintext adds nothing to a vault whose key is already published,
  and everything to one whose key is not.

  This is irreversible on a git-hosted target: plaintext committed to a
  repository stays in its history even if the vault is closed later.

  Either:  sgit publish --with-plaintext --visibility public
  Or:      sgit publish                     (ciphertext only)
```

### Git-hosted irreversibility warning

Printed whenever visibility is `public`, because the output is routinely deployed into a git
repository:

```console
$ sgit publish --visibility public
  note: if you deploy this folder into a git repository, the published bytes
        stay in its history after any later deletion, so rotation cannot
        revoke access to what you publish now.
        Deploy to object storage instead if you may need to revoke.
```

### The two `index.html` files (`07__publish-target.md` §3)

`publish` always emits the loader; a vault's own `index.html` is ciphertext at that moment and
cannot change the output. The two only meet at **deployment**, when someone holding the key
expands plaintext into the served root:

```console
$ sgit publish
Publishing vault q7r6d5zd → .sg_vault/publish/

  Ciphertext objects   13  (15 KB)
  Loader               bundled template (sgit v0.15.6)
  Plaintext surface     3               index.html, cover.json, manifest.json
  Visibility           bare             no vault content in this folder
```

```console
$ sgit deploy ../site-repo/docs --expand        # deployment step; needs the key
  Expanding 13 files …
  note: this vault has its own index.html, so it takes the served root.
        The loader is not written — every file here is already plaintext,
        so there is nothing left for it to unlock.
```

### With published API docs (`08__api-docs.md`)

```console
$ sgit publish --visibility public --api-docs
Publishing vault q7r6d5zd → .sg_vault/publish/

  Ciphertext objects   13  (15 KB)
  Plaintext surface     6               + sgit_public_read_c28b118c…,
                                          api/openapi.json, api/docs/
  API docs             cdn              swagger-ui-dist@5.17.14, SRI-pinned (4 KB added here)
  Visibility           public

Published. The contract describes only what this folder serves: GET, no auth,
ciphertext responses. View it with `sgit vault serve`.
```

Each mode states its own trade-off rather than burying it:

```console
$ sgit publish --api-docs=cdn
  note: Swagger UI loads from cdn.jsdelivr.net, pinned to an exact version with
        SRI hashes and no-referrer, so the CDN cannot change the code or learn
        which vault this is. It does mean the docs page needs the network.
        Use --api-docs=bundled for an offline or no-third-parties deployment.

$ sgit publish --api-docs=bundled
  note: vendoring Swagger UI adds 1.53 MB to this folder — about 2.7× the
        vault itself — and to every copy, zip and mirror of it.
```

---

## 2. `sgit vault serve`

```
sgit vault serve [<dir>] [--port N] [--open] [--bind 127.0.0.1]
```

Browsers give every `file://` document an **opaque origin**, so a loader opened by
double-click cannot fetch the objects beside it. This command is the fix — a feature, not a
documented workaround. It also covers the unpacked-zip case, since unpacking yields a folder.

```console
$ sgit vault serve --open

  Serving   .sg_vault/publish/
  Vault     q7r6d5zd  ·  13 objects  ·  visibility: public
  URL       http://127.0.0.1:8420/
  Loader    http://127.0.0.1:8420/index.html
  API docs  http://127.0.0.1:8420/api/docs/          (when present)

  Why this command exists: browsers give local files an opaque origin, so
  opening index.html directly cannot fetch the objects next to it.

  Read-only. Bound to 127.0.0.1 (use --bind 0.0.0.0 to expose on the LAN).
  Ctrl-C to stop.

  GET /index.html                                            200   1.9 KB
  GET /api/vault/read/q7r6d5zd/bare/refs/ref-pid-muw-1995…   200    69 B
  GET /api/vault/read/q7r6d5zd/bare/data/obj-cas-imm-…       200   8.7 KB
```

With no argument it serves `.sg_vault/publish/`, publishing first if that folder is absent or
stale. A directory argument is still accepted, for serving a folder someone else published:

```console
$ sgit vault serve
  No published folder yet — running `sgit publish` first.
  URL  http://127.0.0.1:8420/
```

Defaults that matter: **bind 127.0.0.1**, **read-only**, **no directory listing**, and it
never serves anything outside the target folder (path-guarded).

---

## 3. `sgit vault mirror` — custody without access

```console
$ sgit vault mirror https://sgit-ai.github.io/SGit-AI__API ./mirror
  Reading manifest.json … 13 objects (15 KB)
  Mirroring   13/13   ████████████████████  done

  Custody without access.
  You now hold a complete, verifiable copy of vault ivpijuvg.
  You cannot read it: no key was used, and none is stored here.
  Verify:  sgit vault mirror --verify ./mirror     (checks every object hash)
  Read it: sgit clone <read-key>:ivpijuvg ./work   (when you have a key)
```

Without a manifest **and** without a host listing it must fail honestly, because no
filename can be derived:

```console
error: cannot mirror without a listing.
  This host offers no directory listing and the folder has no manifest.json,
  so no filename can be derived — every name in a vault comes from the read key.
  Ask the publisher to republish with sgit ≥ 0.15.6 (which always emits a manifest).
```

---

## 4. Loader mockups (Web team implements; shown here so the CLI's output matches)

### Test 9 — no key, no cover: the stranger's first view

```
┌──────────────────────────────────────────────┐
│  🔒  Encrypted vault  ivpijuvg               │
│                                              │
│  This vault is published but not public.     │
│  Its contents are encrypted; this page and   │
│  the host cannot read them.                  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ Paste a read key to open…              │  │
│  └────────────────────────────────────────┘  │
│                    [ Open ]                  │
│                                              │
│  Have a link with a key? Open that instead.  │
│  13 objects · 15 KB · updated 17 Aug 2026    │
└──────────────────────────────────────────────┘
```

### With a cover — a closed vault that is still linkable

```
┌──────────────────────────────────────────────┐
│  [ image ]                                   │
│  Investor Pack — Q3                          │
│  Financials, cap table and board deck for    │
│  the Q3 raise. Contents are encrypted.       │
│                                              │
│  Request access: ir@example.com              │
│  ┌────────────────────────────────────────┐  │
│  │ …or paste a read key                   │  │
│  └────────────────────────────────────────┘  │
│  Updated 17 Aug 2026                         │
└──────────────────────────────────────────────┘
```

### The refusal the key classifier makes possible

```
⚠  That is a VAULT key (sgit_private_vault_…), which can modify this vault.
   This page only ever needs your read key, and should never receive a write key.
   Get it with:  sgit vault derive-keys <your-vault-key>
```

---

## 5. Strings that are load-bearing

Do not soften these without a decision:

| String | Why it matters |
|---|---|
| the `--visibility public` confirmation | it is the only moment a user is told publication is irreversible |
| the plaintext warning on a vault-supplied `index.html` | it is the only notice that a file the user thinks of as content is being published in the clear |
| the `--with-plaintext` refusal | it prevents a permanent, silent mistake |
| the git-history note | rotation does not revoke on a git-hosted target |
| `serve`'s "why this command exists" line | otherwise it reads as an unnecessary server in a serverless product |
| `mirror`'s "you cannot read it" | custody without access is the point, not a limitation |
