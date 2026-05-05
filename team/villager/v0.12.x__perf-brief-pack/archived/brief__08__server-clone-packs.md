# Brief B08 — Server-Side Clone Packs

**Owner role:** **Explorer Architect** (wire format + protocol design) + **Explorer Dev** (server impl) + **Villager Dev** (client consumer)
**Status:** BLOCKED until briefs B07 (diagnosis) + B06 (workflow on clone) land.
**Prerequisites:** B07 + B06 merged.
**Estimated effort:** ~2–4 working days (multi-component, server + client + format spec)
**Touches:**
- Server (FastAPI backend) — new endpoint + pack builder + cache layer
- Client `sgit_ai/sync/Vault__Sync.py` (or step classes) — pack-download path
- Format spec doc

---

## Why this brief exists

Per `design__05__clone-pack-format.md` + decision 5: ship server-side
"clone packs" — a single binary download per (commit, mode) containing
all encrypted immutable objects needed. This is the **load-bearing perf
fix** for clone (and later push/pull/fetch).

---

## Required reading

1. This brief.
2. `design__05__clone-pack-format.md` (the architectural sketch).
3. `design__01__access-modes.md` (the per-mode pack flavours).
4. `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md` (the numbers from B07).
5. The sgraph-ai-app-send FastAPI codebase (separate repo; identify access path with Dinis).
6. Existing client API layer: `sgit_ai/api/Vault__API.py`, `API__Transfer.py`.

---

## Scope

### Phase 1 — Wire format spec (Architect)

Produce: `team/villager/v0.12.x__perf-brief-pack/changes__pack-wire-format.md`

Locks in:
- Magic bytes + version + flavour + commit-id encoding in the header.
- Index entry layout (object-id, offset, length, type byte).
- Index sort order (probably by object-id, ascending).
- Body concatenation rules (any padding? alignment? I'd suggest none — pack tightly).
- Footer checksum (SHA-256 of body) + optional signature.
- Endianness, length field widths, all the boring-but-load-bearing details.

Dinis reviews. Then implementation.

### Phase 2 — Server: pack builder

Implement in the FastAPI backend:
- A `PackBuilder` class that, given (vault_id, commit_id, flavour),
  walks the commit graph (using the existing per-object storage as
  the source of truth), assembles a pack per the wire-format spec,
  and writes it to `<vault storage>/packs/<commit-id>__<flavour>.pack`.
- Pack-build is **idempotent**: re-running for the same (commit, flavour)
  produces byte-identical output.
- A `PackCache` LRU manager that knows which packs exist and which to
  evict under storage budget pressure.
- `pack-index.json` per vault, listing available packs and sizes.

### Phase 3 — Server: HTTP endpoints

Implement in the FastAPI backend:
- `GET /vaults/{vault_id}/packs/{commit_id}/{flavour}` — see design D5 §"Protocol".
- `POST /vaults/{vault_id}/objects/missing` — backfill for missing items in a pack (rare; safety net).
- Authentication: existing read-key header.
- Streaming: ideally stream the pack body as it's being built (don't
  buffer entire pack in memory).

### Phase 4 — Server: pre-warming hook

When `POST /vaults/{vault_id}/refs/{ref_id}` (or whatever endpoint completes
a push) succeeds, fire an async task to build `full` and `head` packs
for the new HEAD commit. Don't block the push response.

### Phase 5 — Client: pack consumer

In the workflow framework (refactored clone from B06), introduce a new
`Step__Clone__Download_Pack`:
- Detect server pack support via a feature-detection probe (or just try
  `GET /packs/...` and fall back to per-object on 404).
- If pack is available: download, verify checksum, unpack into
  `bare/data/{id}` for each object in the index.
- If not (old server, or pack still building with 202 retry): fall
  back to existing `Step__Clone__Walk_Trees` + `Step__Clone__Download_Blobs`
  per-object behaviour.
- Step output: pack metadata (size, object count, source URL).

The decision lives at the workflow-graph level: `Workflow__Clone`
becomes:

```
1. derive_keys
2. check_directory
3. download_index
4. download_branch_meta
5. walk_commits
6a. try_download_pack       # NEW: returns Maybe<Pack>
    ├─ if pack OK → unpack into bare/data/, skip 6b + 7
    └─ if pack unavailable → continue to 6b + 7
6b. walk_trees              # FALLBACK
7.  download_blobs          # FALLBACK
8.  create_clone_branch
9.  extract_working_copy
10. setup_local_config
```

### Phase 6 — Tests

- Server-side: pack-builder tests with synthetic vaults; pack-cache tests; endpoint tests.
- Client-side: download-pack tests with a server fixture serving a precomputed pack; fallback test against a no-pack server.
- End-to-end: clone the case-study vault using packs; verify byte-identical `bare/` against the per-object clone.
- Performance regression: clone the case-study vault, target ≤ 30s (down from 202s) — exact target informed by B07's diagnosis.

### Phase 7 — Diagnosis re-run

Re-run brief B07's diagnosis with packs enabled. Save as `changes__case-study-diagnosis-post-packs.md`. Compare to the baseline.

---

## Hard constraints

- **Encryption preserved.** Server packs ciphertext only. Zero-knowledge guarantee untouched.
- **Pack format versioned.** Magic + version bytes in every pack. Old clients see new pack version → friendly error or fallback.
- **Backward compat at protocol level.** Old clients ignore new endpoint. New client falls back gracefully if server lacks pack support.
- **Type_Safe** for all new client schemas (pack metadata, pack index entries).
- **No mocks** in client tests. Real fixture pack files; real in-memory FastAPI test server (or comparable).
- **No `__init__.py` under `tests/`.**
- Coverage on new client code ≥ 85%.
- Suite must pass under Phase B parallel CI shape.
- Performance regression target: case-study clone ≤ 30s.

---

## Acceptance criteria

- [ ] Wire-format spec doc exists and is Architect+Dinis-approved.
- [ ] Server pack builder + cache implemented + tested.
- [ ] Server endpoints implemented + tested.
- [ ] Pre-warming hook fires on push completion.
- [ ] Client `Step__Clone__Download_Pack` implemented + tested.
- [ ] Fallback path (no pack support) tested.
- [ ] End-to-end byte-identical assertion passes.
- [ ] Case-study clone ≤ 30s (or document why not + propose follow-up).
- [ ] Diagnosis re-run doc exists.
- [ ] Suite ≥ existing test count + N passing; coverage delta non-negative.

---

## Out of scope

- Per-mode pack flavours beyond `full` and `head` — defer `bare-*` and `range` to brief B09.
- Migration of existing vaults to a new storage shape (brief B10).
- Generalising packs to push / pull / fetch (brief B11).
- CDN / multi-region pack distribution.
- Pack signing (note as residual security future-work; AppSec follow-up).

---

## Deliverables

1. Wire-format spec doc.
2. Server source (sgraph-ai-app-send): pack builder, cache, endpoints, pre-warming hook, tests.
3. Client source: `Step__Clone__Download_Pack`, schemas, fallback wiring, tests.
4. Diagnosis re-run doc.
5. Closeout note in sprint overview.

---

## When done

Return a ≤ 350-word summary:
1. Final wire format (1-paragraph headline).
2. Server pack-build cost + cache hit rate (measure with a synthetic warm-cache test).
3. Client clone time post-packs vs baseline (case-study vault).
4. Fallback path verified working.
5. Coverage + test count deltas.
6. Anything that surfaced about the format that should be reflected back into design D5.
