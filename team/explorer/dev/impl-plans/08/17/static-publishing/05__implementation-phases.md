# 05 — Implementation Phases

Each phase is independently shippable: one PR, green suites, its own acceptance criteria.
**Start with P1 and P3** — together they are demonstrable value and commit to nothing in
the publish protocol that is still under discussion.

| Phase | Deliverable | Depends on | Size | Risk |
|---|---|---|---|---|
| P1 | Static read transport, productionised | — | S | low |
| P2 | `sgit publish` (the plaintext surface) + `manifest.json` | P1 | M | **medium** |
| P3 | `sgit vault serve` | — | S | low |
| P4 | `--visibility`, cover, downgrade warning | P2 | M | **medium** |
| P5 | `sgit vault mirror` (custody) | P2 | S | low |
| P6 | Bundles | P2 | M | low |
| P4b | Published API docs (`--api-spec` / `--api-docs`) | P2 | S | low |
| P7 | Invariants + 14 cells as a suite | P1–P5 | M | — |
| P8 | `sgit vault expand` — deployment-time plaintext expansion | P2 | M | **deferred — not in v1** (decision 11) |

---

## P1 — Static read transport

**The design already exists as running code.** Promote
`scripts/spike__static_vault_transport.py`; do not redesign it.

**Files**
- `sgit_ai/network/api/Vault__API__Static.py` — subclass of `Vault__API`; overrides
  `read`, `batch_read`, `presigned_read_url`, `list_files`; `write`/`delete`/`batch` raise.
- `sgit_ai/safe_types/Enum__Transport.py` — `AUTO | API | STATIC | LOCAL`.
- `sgit_ai/core/Vault__Errors.py` — add `Vault__Read_Only_Transport_Error`.
- `sgit_ai/cli/CLI__Main.py` — `--transport` on the network parent parser.
- `sgit_ai/cli/CLI__Vault.py` — resolve transport at the boundary; report it in `vault info`.
- Tests: `tests/unit/network/api/test_Vault__API__Static.py`,
  `tests/unit/safe_types/test_Enum__Transport.py`.

**Acceptance**
- [ ] `sgit clone` works from: a local folder, a `ThreadingHTTPServer` over a folder, and a
      real Pages URL (integration).
- [ ] Both layouts (`api/vault/read/{vid}/{fid}` and `{fid}`) sniff correctly, sticky after
      the first success.
- [ ] Large-blob path works — `presigned_read_url` returns the object's own URL. **Add a
      >4 MB fixture**; small fixtures will not catch this.
- [ ] Writes raise `Vault__Read_Only_Transport_Error` with an actionable message.
- [ ] A 404 is `None` (absent), not an exception; per-object failures never abort the run.
- [ ] Resolved transport appears in `sgit vault info`.

**Watch out:** local fan-out should be 1 worker (parallelism on `open()` is pure overhead);
HTTP default 8.

---

## P2 — `sgit publish` (the plaintext surface) + `manifest.json`

**Files**
- `sgit_ai/core/actions/publish/Vault__Publish.py`
- `sgit_ai/schemas/publish/Schema__Published_Manifest.py`,
  `Schema__Published_Object.py`, `Schema__Plaintext_Entry.py`
- `sgit_ai/safe_types/Enum__Published_Layout.py` (`API_PATH | FLAT`),
  `Enum__Visibility.py` (`BARE | NAMED | PUBLIC` — used fully in P4)

- `sgit_ai/cli/CLI__Publish.py`; wire in `CLI__Main.py`
- Tests: `tests/unit/core/actions/publish/…`, `tests/unit/schemas/publish/…`

**Acceptance**
- [ ] `sgit publish` takes **no output-directory argument**, and the only path that changes is
      `.sg_vault/publish/` — asserted by hashing the work tree before and after
      ([`07__publish-target.md`](07__publish-target.md) §6, part of this phase).
- [ ] `.sg_vault/publish/` contains **no vault content**: publish a vault holding its own root
      `index.html` and assert the emitted loader is byte-identical to the bundled template
      (`07` §3). Content expansion is a deployment-time act, not part of `publish`.
- [ ] The output contains **no ciphertext** and no `api/vault/read/` subtree — the store is
      composed in at deployment (r9). Publish a large-store fixture; assert the folder is
      O(KB) and byte-count-independent of the vault.
- [ ] `manifest.json` lists every object with size, the ordered commit list (walked from the
      head **via parents** — walking a commit log misses the init commit's empty trees), the
      head, and the hashed plaintext surface.
- [ ] The plaintext surface comes from a **fixed allow-list of names in code**, and is
      entirely *generated* — assert that **no file from the vault**, at any path, appears in
      the output at `--visibility bare`.
- [ ] Every schema round-trips (`from_json(x.json()).json() == x.json()`).
- [ ] Publishing the same vault twice produces identical bytes (deterministic).
- [ ] Publish runs with **only the read key** available (no `local/vault_key`) — proven
      possible by the `10` tabletop, step 9; this is what makes CI republish work.
- [ ] `manifest.json` `objects[]` entries carry `sha256` of the ciphertext, so a keyless
      mirror can verify non-content-addressed files too (refs/indexes/keys — `10` step 7).

**Risk:** this phase owns the plaintext boundary. If in doubt, emit less.

---

## P3 — `sgit vault serve`

**Files**
- `sgit_ai/network/serve/Vault__Static_Server.py` — stdlib `ThreadingHTTPServer`,
  read-only, no directory listing, path-guarded with `Vault__Path_Guard`.
- `sgit_ai/cli/CLI__Serve.py`; wire in `CLI__Main.py`.
- Tests: `tests/unit/network/serve/test_Vault__Static_Server.py`.

**Acceptance**
- [ ] Serves the surface at `/` and **routes** `/api/vault/read/<vid>/bare/*` to
      `.sg_vault/bare/*` (virtual composition — no copies); GETs return byte-identical
      content (I1).
- [ ] Binds `127.0.0.1` by default; `--bind` widens and says so loudly.
- [ ] Path traversal is impossible — `GET /../../etc/passwd` and encoded variants refused
      (reuse the existing traversal test payloads).
- [ ] No writes: any non-GET/HEAD returns 405.
- [ ] `--port 0` picks a free port and prints it (needed by tests).
- [ ] No argument → serves `.sg_vault/publish/`, publishing first if it is absent or
      **stale** — defined as: `sha256(bare/refs/<ref_id>)` differs from the sha256 the
      manifest recorded for that file (a keyless compare; the manifest enumerates the store
      with hashes, so staleness needs no crypto — v1 review R4/R7).
- [ ] Help text explains **why** the command exists (the opaque-origin rule).

**Watch out:** no new dependency. The product's claim is that no server is needed; this one
is a local convenience and must look like it.

---

## P4 — Visibility, cover, and the downgrade warning

**Files**
- `sgit_ai/schemas/publish/Schema__Vault_Cover.py` (`title`, `description`, `image`,
  `updated`, `access`, `public`)
- visibility recorded in **per-clone local config** (`.sg_vault/local/config.json`), never
  in the vault — a clone must not inherit somebody else's publishing settings (decision 5)
- `Vault__Publish` — emit `sgit_public_read_<hex>` only when `PUBLIC`; the confirmation
  prompt; the **visibility-downgrade warning** (`02` §1); the git-history note.

**Acceptance**
- [ ] Republishing with a resolved visibility **below** the existing output's manifest
      warns and requires `--visibility public` or `--yes` (the CI fresh-clone case).
- [ ] `--visibility public` prompts unless `--yes`, and the prompt states irreversibility.
- [ ] The published key file uses `format_read_key(hex, public=True)` →
      `sgit_public_read_<hex>`.
- [ ] Visibility is **recorded per clone**, so a republish cannot silently flip private →
      public by inheriting a different default — **and a fresh clone defaults to `bare`**
      rather than inheriting the publisher's choice.
- [ ] Git-hosted output prints the history note.
- [ ] `sgit_private_*` can never appear as a published filename — assert it.

---

## P4b — Published API docs

Full design and acceptance criteria: [`08__api-docs.md`](08__api-docs.md).

**Files:** `sgit_ai/core/actions/publish/Vault__Publish__Api_Docs.py`;
`Schema__OpenAPI_Document.py`; `Enum__Api_Docs_Mode.py` (`CDN | BUNDLED`);
`sgit_ai/network/assets/Swagger_UI__Assets.py` (fetch-verify-cache, bundled mode only).

**Acceptance:** the checklist in `08` §7. Three that are easy to miss: `servers` must be
relative (`"."`) so the file works on any host and any path prefix; the emitted artefacts
must join the **declared plaintext surface** in `manifest.json` with their hashes; and the
CDN mode's five required attributes (exact version pin, `integrity`, `crossorigin`,
`referrerpolicy`, CSP meta) are each individually asserted.

**Packaging note:** sgit ships **no** Swagger UI bytes. `=cdn` (the default) emits ~4 KB of
HTML; `=bundled` fetches the pinned files once, verifies them against the same SRI hashes,
and caches them under `~/.sgit/assets/swagger-ui/<version>/`. Measured sizes and the pinned
hashes are in `08` §2.2 and §4.

---

## P5 — `sgit vault mirror` (custody without access)

**Files:** `sgit_ai/core/actions/mirror/Vault__Mirror.py`, `sgit_ai/cli/CLI__Mirror.py`.

**Acceptance**
- [ ] Mirrors from a manifest with **no key material anywhere in scope**; result is
      byte-identical to the source.
- [ ] Every object verified against `sha256(ciphertext)[:12]` == its id.
- [ ] `--verify` re-checks an existing mirror without fetching.
- [ ] No manifest and no listing → the honest failure message from `02`.
- [ ] Writes no key file, and says plainly that the copy is unreadable.

---

## P6 — Bundles (deferrable)

**Files:** `sgit_ai/core/actions/publish/Vault__Publish__Bundles.py`.

**Acceptance**
- [ ] `bundles/head-<commit>.zip` (snapshot) and `bundles/<commit>.zip` (per-commit delta).
- [ ] **`ZIP_STORED`, never `ZIP_DEFLATE`** — ciphertext is incompressible; DEFLATE measured
      *larger* (1.078× vs 1.075×) at ~10× the CPU.
- [ ] Immutable names keyed by commit id; never `latest.zip`.
- [ ] Bundles are **derived, never authoritative**: a missing/corrupt bundle degrades to
      loose-object fetches, never to a wrong result. Test with a deliberately corrupted bundle.
- [ ] Every object extracted from a bundle is verified against its id.
- [ ] The union of per-commit deltas reconstructs `bare/data/` exactly (walk parents).

---

## P7 — The suite

See `04__invariants-and-tests.md`. Build the six invariants first — they cover the most
risk per line — then the cells in the order given there.

---

## Reuse, don't rebuild

| Need | Already exists |
|---|---|
| static transport | `scripts/spike__static_vault_transport.py` |
| key classification / public form | `Vault__Crypto.classify_key`, `format_read_key(public=True)` (`67c2ab6`) |
| path containment | `sgit_ai/storage/Vault__Path_Guard.py` |
| integrity | ids are `sha256(ciphertext)` — verification needs no key |
| local server harness | `tests/integration/conftest.py` |
| bundle economics | `scripts/spike__measure_commit_bundles.py` |
