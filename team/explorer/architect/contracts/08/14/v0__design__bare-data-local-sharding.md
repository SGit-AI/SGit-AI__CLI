# Design — Local Sharding of `bare/data/` (256-bucket fan-out)

**Version:** v0 (proposal — awaiting maintainer sign-off)
**Date:** 2026-08-14
**Role:** Architect (Explorer)
**Problem:** `.sg_vault/bare/data/` is a single flat directory holding every
CAS object. A vault clone committed to a git repo hits GitHub's UI limits
(directory listings truncate at 1,000 files; PR diffs stop rendering around
3,000 changed files), and very large flat directories degrade filesystem and
`git status` performance. Git itself has no hard cap — the pain is tooling and
UI — but the standard fix is the same one git uses for its own object store:
fan out into 256 subdirectories keyed by the leading hex of the hash.

---

## 1. The two names of an object — what may change and what must not

Every object has exactly two names, and the whole design rests on keeping them
separate:

| Name | Example | Who shares it | May shard? |
|---|---|---|---|
| **Wire file_id** | `bare/data/obj-cas-imm-005f23380724` | Server storage keys, SG/Vault web, every past sgit version, batch ops, presigned URLs, change packs | **NO — frozen contract** |
| **Local disk path** | `.sg_vault/bare/data/obj-cas-imm-005f23380724` | This clone's filesystem only | **YES** |

The data model never stores a *path*: trees, commits, refs and indexes
reference **object ids**, and the local path is derived from the id at access
time. So the maintainer's intuition is correct — moving the next object to
`bare/data/00/obj-cas-imm-005f23380724` on disk changes nothing about what any
index or tree says. The server does not need sharding at all (S3 keyspace is
flat), and SG/Vault web only ever speaks wire file_ids, so **server and browser
are untouched by construction** — provided the wire name never changes.

### The trap that makes this non-trivial

`_upload_bare_to_server` (`Vault__Sync__Push.py:592`) derives wire file_ids
**from local relative paths** (`os.path.relpath` over a walk of `bare/`). With
naive local sharding it would upload `bare/data/00/obj-...` as the wire id —
publishing a second, differently-named copy of every object and corrupting the
vault for every other client. Any sharding change MUST first make wire-id
derivation id-based, never path-based, at this site (strip the shard segment
when the walked path is under `bare/data/`).

### Prefix-splitting is a no-op

All of `bare/data/` shares the single prefix `obj-cas-imm-` (blobs, trees and
commits are all immutable CAS objects; refs live in `bare/refs/`, caches in
`bare/cache/`, indexes in `bare/indexes/` — all small populations). Splitting
by id prefix therefore buys nothing. Shard on the **first two hex characters
of the hash tail**: `obj-cas-imm-005f23380724` → `bare/data/00/…`. 256 buckets
keeps a clone under GitHub's 1,000-file listing truncation up to ~256k objects
(and under 3,000/bucket to ~768k).

---

## 2. Step zero — centralise path resolution (a bug-surface fix on its own)

`Vault__Object_Store.object_path()` is the canonical resolver, but roughly a
dozen sites hand-build `os.path.join(sg_dir, 'bare', 'data', oid)`:

`Vault__Sync__Pull.py:250` · `Vault__Sync__Sparse.py:101,114,167` ·
`Vault__Sync__Fsck.py:195` · `Vault__Sync__Upload_Objects.py:30` ·
`Step__Move__Validate_Local.py:181` · `Step__Move__Build_Temp_Vault.py:111-112`
· `Vault__Sync__Base.py:342,366` (fetch_tree_lazy) · `CLI__Vault.py:500` —
plus `all_object_ids()`/`total_size()` which flat-`listdir`.

Phase 1 of this work routes every one of them through the object store (or a
new `Vault__Storage.object_path(directory, oid)` for sites without a store
instance) and adds an architecture test in the spirit of
`test_Layer_Imports.py` that greps the tree for hand-built `bare/data` joins so
the centralisation cannot rot. This phase changes zero behaviour and is worth
shipping alone.

## 3. The sharded layout

- Shard key: `oid.removeprefix('obj-cas-imm-')[:2]` (2 lowercase hex chars).
- Local path: `.sg_vault/bare/data/{shard}/{oid}`. Filename keeps the FULL id
  (unlike git, which strips the fanout chars from the filename) — so a file is
  self-identifying, recovery/debugging tools keep working, and the flat wire id
  is recomputable from the filename alone.
- Layout marker: `.sg_vault/local/layout.json` → `{"object_layout": "sharded-v1"}`.
  Absent marker = flat (every existing clone).

### Resolution rules (new code, both layouts, forever)

- **Read** (`load`/`exists`): try the layout's primary location, then the other
  one. Cost: one extra `os.path.isfile` on miss only.
- **Write** (`store`/`store_raw`/`store_at`): follow the clone's marker.
- **Enumerate**: `all_object_ids()` walks both the flat dir and shard subdirs
  (skipping non-2-hex-named entries so `bare/data` stays future-proof).

## 4. Rollout — minimal side effects, in order

1. **Phase 1 (no behaviour change):** centralise path resolution + the
   anti-rot architecture test + fix `_upload_bare_to_server` to derive wire
   ids from ids, not paths.
2. **Phase 2 (opt-in):** implement dual-layout resolution + a
   `sgit maintenance shard` command (move files bucket-by-bucket, fsync, write
   the marker last; idempotent and resumable — a crash mid-migration leaves a
   mixed layout that dual-read already handles). `sgit fsck` learns to verify
   both layouts and report bucket balance.
3. **Phase 3 (flip the default):** after a release of soak time, `init`/`clone`
   create sharded clones by default. Existing clones stay flat until the owner
   runs the migration — nothing ever migrates implicitly.

### Compatibility matrix

| Actor | Effect |
|---|---|
| Server / existing vault data | none — wire ids unchanged, server never sees layout |
| SG/Vault web (any version) | none — speaks wire ids only |
| Past sgit on an **existing (flat) clone** | none — flat clones stay flat |
| Past sgit on a **sharded clone** | breaks (cannot find objects) — the ONLY incompatibility. Sharded is opt-in in Phase 2 precisely so a user sharing one clone directory between CLI versions makes that choice knowingly; the marker file gives a clear diagnostic |
| New sgit on any clone | works — dual-layout read is unconditional |

## 5. Tests that gate this

- Round-trip on a sharded clone: init→commit→push→clone→pull with wire-id
  assertions (`list_files` must show FLAT ids while local disk is sharded —
  the direct falsifier for the §1 trap).
- Migration: flat→sharded on a populated vault, interrupted-migration resume,
  double-run idempotence.
- Mixed-layout read correctness; `_upload_bare_to_server` from a sharded clone
  produces flat wire ids (regression for the trap).
- The anti-rot grep test from Phase 1.

## 6. Open decisions for the maintainer

1. Approve `sharded-v1` as opt-in first (Phase 2) with default-flip later
   (Phase 3)? The alternative — sharding new clones immediately — is safe for
   the ecosystem but surprises anyone pointing an old CLI at a new clone.
2. Should `sgit maintenance shard` exist in reverse (`--flatten`) as an escape
   hatch for old-CLI interop? (Cheap: same mover, opposite direction.)
