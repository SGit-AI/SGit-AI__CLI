# Design — Server-Side Clone Pack Format

**Status:** Architectural sketch. Detailed wire format designed in brief B08.
**Owners:** **Explorer Architect** (format design + protocol), Villager Dev (client-side consumer).

## The principle

> The server precomputes a single binary "clone pack" containing all the
> immutable encrypted objects a client needs to clone to a given state.
> One HTTP request, one decompress, decrypt-and-stream into the local
> object store.

Pack contents are **encrypted ciphertext only** — server cannot read them.
Zero-knowledge guarantee preserved.

## What goes in a pack

A pack is a binary container. Sections:

| Section | Purpose |
|---|---|
| Header | Magic bytes + version + pack flavour + commit-id + creation timestamp |
| Index | Object-id → (offset, length, type) — typed index of everything in this pack |
| Body | Concatenated encrypted object blobs in CAS-id order |
| Footer | Checksum (SHA-256 of body), optional signature |

The index is what the client uses to know which objects are in the pack
(and skip ones it already has). The body is just a concatenation; objects
are still individually-decryptable by the client.

## Pack flavours (per access mode)

Per `design__01__access-modes.md`, each clone mode needs a different
object set. Server precomputes one pack per (commit-id, flavour):

| Flavour | What's in it |
|---|---|
| `full` | All commits ancestral to commit-id + all reachable trees + all reachable blobs |
| `head` | All commits + only HEAD-rooted trees + all reachable blobs |
| `bare-full` | All commits + all reachable trees (no blobs) |
| `bare-head` | All commits + only HEAD-rooted trees (no blobs) |
| `range:<from>..<to>` | Commits in range + trees + blobs reachable in the range |
| `tree-history` | Historical trees only (consumed by `clone-branch` lazy fetch) |

Most-common flavours (`full`, `head`) are pre-warmed at push time. Less
common flavours (`range`, `bare-*`) are computed on first request and
cached.

## Pre-warming at push time

When a push completes, the server knows the new HEAD commit-id. It can
asynchronously precompute `full` and `head` packs for that commit-id.
First clone after a push hits the pack cache.

This means: **good clones are fast; the first clone after a push pays
the pack-build cost on the SERVER not the client.**

## On-disk shape (server)

FastAPI side. Packs live alongside individual objects:

```
<server vault storage>/
├── data/                       individual encrypted objects (existing)
│   └── <object-id>
├── packs/                      NEW
│   ├── <commit-id>__full.pack
│   ├── <commit-id>__head.pack
│   ├── <commit-id>__bare-full.pack
│   └── <commit-id>__bare-head.pack
└── pack-index.json             commit-id → available flavours + sizes
```

Packs are immutable once written. Eviction by LRU when storage budget
is exceeded; eviction does not lose data — packs can always be
regenerated from individual objects.

## On-disk shape (client)

Client unpacks into the existing `bare/data/{id}` layout. Pack itself
is not retained client-side; only the unpacked objects.

```
.sg_vault/bare/data/
├── <object-id>          (unpacked from pack)
├── <object-id>          (unpacked from pack)
└── ...
```

The client's local object store stays at the existing format — no
client-side migration needed for adopting packs.

## Protocol

New FastAPI endpoint:

```
GET /vaults/{vault_id}/packs/{commit_id}/{flavour}
    Headers:  x-sgraph-read-key   (so server can authenticate read access)
    Returns:  the pack bytes (binary)
              or 404 if commit not found
              or 202 + Retry-After if pack is being built
```

Optional companion endpoint for missing-object backfill:

```
POST /vaults/{vault_id}/objects/missing
    Body:     {"object_ids": ["...", "...", ...]}
    Returns:  {"<id>": "<base64-encrypted-blob>", ...}
```

Used when the client's pack index has misses (rare; happens only when
the pack was built before some referenced object existed, which
shouldn't happen for immutable packs but the safety net is cheap).

## Client-side consumption

In the workflow framework (`design__04`), the `Step__Clone__Walk_Trees`
and `Step__Clone__Download_Blobs` steps are subsumed (or
short-circuited) by a new `Step__Clone__Download_Pack` step:

```
walk_commits              → still runs (commits are tiny, useful cache)
download_pack             → NEW; one HTTP, populates bare/data/
walk_trees                → still runs but is now disk-only (fast)
download_blobs            → still runs but is mostly no-op
```

The pack download IS the network cost; everything after is local.

## Backward compatibility

- **Old vaults**: server can build packs on demand from individual
  objects. No vault-format change for the on-disk format.
- **Old clients**: keep the per-object `batch_read` endpoint. They
  ignore packs.
- **New clients on old servers**: detect missing pack endpoint
  (404 / not-found), fall back to per-object download.
- **Vault migration command** (brief B10): not strictly needed for
  packs (server side is authoritative). Migration command is for
  any client-side format additions (e.g., `.sg_vault/work/`).

## Encryption + Zero-knowledge

- Pack body is concatenated **ciphertext** objects. Server does not
  see plaintext.
- Pack index lists object-ids and offsets — same metadata the server
  already exposes via per-object endpoints. No new information leak.
- Pack footer signature (optional) lets clients verify the pack came
  from the legitimate server endpoint, mitigating man-in-the-middle.

## What this design leaves to brief B08

- Exact wire format (binary layout, magic bytes, versioning).
- Pack-build cost and async strategy on the server.
- Pack cache eviction policy.
- Performance budgets (pack size for typical vaults, build time).
- Streaming support (do we stream the pack as we build, or build-then-serve?).

## Acceptance for this design

- Pack flavours per mode are agreed.
- On-disk shape (server + client) is agreed.
- Protocol shape is agreed.
- Encryption / zero-knowledge property is agreed.
- Backward-compat strategy is agreed.

Brief B08 produces the wire format spec + initial implementation; brief B09 wires the pack consumer into the workflow steps.
