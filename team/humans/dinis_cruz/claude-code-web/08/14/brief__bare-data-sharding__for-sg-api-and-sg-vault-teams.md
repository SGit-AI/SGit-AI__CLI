# Briefing — Sharding sgit's `bare/data/` Object Store

**To:** SG/API (Send) team · SG/Vault (web) team
**From:** sgit CLI team (Explorer / Architect)
**Date:** 2026-08-14 · **Status:** PROPOSAL — your review requested before any implementation
**Full design:** `team/explorer/architect/contracts/08/14/v0__design__bare-data-local-sharding.md` (SGit-AI__CLI repo)

You two teams know exactly how vaults are accessed via the API and from the
web. Our claim is that this change **requires nothing from either of you** —
and that claim is precisely what we want you to attack. §5 has the specific
questions; everything before it is the context needed to answer them.

---

## 1. The problem

A vault clone stores every CAS object in ONE flat directory:

```
.sg_vault/bare/data/obj-cas-imm-005f23380724
.sg_vault/bare/data/obj-cas-imm-00a1b2c3d4e5
… (one file per blob, tree, and commit — thousands for a real vault)
```

Users increasingly commit vault clones into git repositories (backup, CI,
GitOps-style workflows). GitHub's web UI truncates directory listings at
1,000 files and stops rendering PR diffs around 3,000 changed files, and very
large flat directories degrade filesystem and `git status` performance. This
is the same problem git itself solved by fanning its object store into 256
subdirectories — and that is exactly the fix we propose, **for the local
clone layout only**.

## 2. The core design fact: an object has two names

| Name | Example | Shared with |
|---|---|---|
| **Wire file_id** | `bare/data/obj-cas-imm-005f23380724` | server storage keys, batch ops, presigned URLs, `list?prefix=`, SG/Vault web, every past sgit |
| **Local disk path** | `.sg_vault/bare/data/obj-cas-imm-…` | that one clone's filesystem, nobody else |

Trees, commits, refs and indexes reference **object ids**, never paths — both
names are derived from the id at the moment of use. The proposal shards ONLY
the local path:

```
.sg_vault/bare/data/00/obj-cas-imm-005f23380724     ← local, new
bare/data/obj-cas-imm-005f23380724                  ← wire, UNCHANGED, forever
```

Shard key = first two hex chars of the id tail → 256 buckets (~256k objects
before any bucket re-approaches GitHub's listing limit). Filenames keep the
full id, so every file stays self-identifying and the flat wire id is always
recomputable from the filename alone. Everything in `bare/data/` shares the
`obj-cas-imm-` prefix (all immutable CAS), so hash-fanout is the only split
that does anything; `bare/refs/`, `bare/cache/`, `bare/indexes/` are small
populations and stay untouched.

## 3. Why this should not touch your systems (the claim to attack)

- **Server:** stores opaque bytes at the file_ids clients send. Wire ids do
  not change, so existing vault data, S3 keys, batch semantics, presigned
  flows and `list?prefix=bare/data/` behave identically. S3's keyspace is
  flat; it does not care about our local folders.
- **SG/Vault web:** as we understand it, the browser addresses objects only
  by full wire file_id (computed from ids it reads out of decrypted trees /
  refs) and never enumerates or mirrors the `bare/data/` *folder structure*.
  If that understanding is right, the web client cannot observe this change.
- **Past sgit versions:** existing clones stay flat and keep working. The
  ONLY incompatibility in the matrix: a clone that has *opted in* to sharding,
  opened by an old CLI (it won't find objects). Sharding is opt-in per clone
  (marker file + `sgit maintenance shard` command) precisely so that is a
  deliberate choice; new sgit reads BOTH layouts unconditionally, forever.

We found (and will fix first) the one place our own code would have broken
this: the CLI's bootstrap re-sync derives wire ids from local *relative
paths* rather than ids — under sharding it would have published
`bare/data/00/obj-…` wire ids. That is an sgit bug to fix regardless, and it
is the cautionary tale behind §5's questions: path-derived assumptions hide
in corners.

## 4. Implementation strategy (in the CLI repo)

1. **Phase 1 — centralise (zero behaviour change):** route the ~12 code sites
   that hand-build `…/bare/data/{id}` paths through the one resolver; fix the
   path-derived wire-id site; add an architecture test so it cannot rot.
2. **Phase 2 — opt-in sharding:** dual-layout read everywhere; layout marker;
   `sgit maintenance shard` migration (idempotent, resumable, reversible via
   `--flatten`); fsck verifies both layouts.
3. **Phase 3 — default for new clones**, after a release of soak. Existing
   clones never migrate implicitly.

Gate tests include: a sharded clone must produce byte-identical wire traffic
to a flat one (the direct falsifier of the whole claim).

## 5. What we need from you

**SG/API (Send) team — please confirm or refute:**

1. Does anything server-side parse or assume the *structure* of `bare/data/`
   file_ids beyond treating them as opaque keys under a prefix (analytics,
   backup tooling, lifecycle rules, migration scripts, the change-pack /
   GC paths)?
2. Are there server-side consumers that *enumerate* `bare/data/` and would be
   confused if a client-side layout ever leaked into wire ids by mistake?
   (We gate against it, but if you have cheap server-side validation of
   file_id shape — e.g. reject `bare/data/` ids containing a `/` — that
   would convert our worst-case bug into a clean 4xx, and we would welcome it.)
3. Forward-looking: is there any *server-side* interest in sharded wire ids
   (S3 prefix partitioning at very high request rates)? We are NOT proposing
   it — it would be a breaking cross-runtime format bump — but if it is ever
   on your roadmap we should bundle it with the already-scheduled 48-bit→256-bit
   object-id widening rather than shipping two migrations.

**SG/Vault (web) team — please confirm or refute:**

4. The web client addresses vault objects **only** by full wire file_id and
   never lists `bare/data/` or reconstructs its folder layout — correct?
   Including in less-obvious corners: export/download features, IndexedDB or
   cache mirrors, service workers, debugging tools?
5. Is there any feature (existing or planned) where the web produces or
   consumes an on-disk `.sg_vault` directory (zip export/import of a clone,
   drag-in restore)? If yes, it needs the same dual-layout read rule — we
   will hand you the resolver spec (~15 lines) if so.

**Both teams:** anything else in your systems where "one file per object in
one folder" is an assumption rather than an implementation detail?

## 6. Heads-up on a related change already shipping (action for SG/Vault web)

Independent of sharding: new sgit releases now display **self-identifying key
prefixes** — `sgit_private_vault_{passphrase}:{vault_id}` and `sgit_private_read_{64-hex}` — so
leaked keys are recognisable by secret scanners and git hooks. The value
after the prefix is byte-identical to the legacy key; nothing cryptographic
changed, and the CLI accepts both forms everywhere.

Impact on you: **users will start pasting prefixed keys into the web UI.**
The web should strip a leading `sgit_private_vault_` / `sgit_private_read_` on key input (two
`startswith` checks) and, when convenient, display the prefixed form on key
output. Until then, users on current web versions simply paste the part after
the prefix — and sgit deliberately keeps embedding the BARE key in the
`vault.sgraph.ai/...#key` URLs it prints, so shared links keep opening on
today's web. Tell us when input-stripping ships and we will switch the URLs
to the prefixed form.

---

*Please route answers to the maintainer (Dinis) or as comments on this file's
PR. Nothing in §1–4 is implemented yet beyond design; Phase 1 (pure
centralisation, zero behaviour change) is the only part we would start before
hearing from you.*
