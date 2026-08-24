# 05 — Implementation Phases

Each phase is independently shippable: one PR, green suites, its own acceptance criteria.
**Start with P1 and P3** — together they are demonstrable value and commit to nothing in
the publish protocol that is still under discussion.

| Phase | Deliverable | Depends on | Size | Risk |
|---|---|---|---|---|
| P0 | Tracked-wins in the ignore engine, then `.github/` ignored by default | — | S | low — **ordering-critical** (decision 17) |
| P1 | Static read transport, productionised | — | S | low |
| P2 | `sgit publish` (the plaintext surface) + `manifest.json` | P1 | M | **medium** |
| P3 | `sgit vault serve` | — | S | low |
| P4 | `--visibility`, cover, downgrade warning | P2 | M | **medium** |
| P5 | `sgit vault mirror` (custody) | P2 | S | low |
| P6 | Bundles | P2 | M | low |
| P4b | Published API docs (`--api-spec` / `--api-docs`) | P2 | S | low |
| P7 | Invariants + 14 cells as a suite | P1–P5 | M | — |
| P8 | `sgit vault expand` — deployment-time plaintext expansion | P2 | M | **deferred — not in v1** (decision 11) |
| P9 | `sgit vault attach` — bind a key to an existing `.sg_vault/bare` checkout | — | S | low — **CI-blocking** (decision 14) |

---

## P0 — Tracked-wins, then `.github/` ignored by default

Decision 17. **The order matters and is the whole phase:** adding `.github` to
`ALWAYS_IGNORED_DIRS` on its own would remove already-tracked `.github/**` from the next
push of an existing vault. Ship the exemption first, the list change second — ideally in
that order even within the same PR.

**Files** *(corrected r15 — the original call-site reference was wrong, found by
implementation: `Vault__Sync__Push.py:771-773` is `_check_no_conflict_files`, a pre-push
scan for leftover `.conflict` files; pruning there never affects the pushed tree. Push does
not walk the work tree for content at all — it diffs commit trees and rejects dirty trees.
The walk that turns tracked `.github/**` into deletions is
`Vault__Sync__Base._scan_local_directory` (used by status, commit and pull), and the same
prune is repeated in `Vault__Branch_Switch`, `Vault__Stash`, `Vault__Revert`,
`Vault__Merge` (×2), `Vault__Diff` and `Vault__Bare` — roughly eight sites, so the
exemption must live in the engine, not at one call site.)*
- `sgit_ai/core/Vault__Ignore.py` — the tracked-wins rule lives IN the engine
  (`load_tracked_paths` / `load_tracked_from_vault`); then `.github` added to
  `ALWAYS_IGNORED_DIRS`.
- `sgit_ai/core/Vault__Head_Paths.py` — resolves the working branch's head path set the
  same way status/commit do, best-effort, feeding every walk site.
- All work-tree walks load the tracked set (one line each).
- `sgit_ai/core/actions/admin/Vault__Ignore__Apply.py` + `sgit vault ignore` — the escape
  hatch the migration notice names (it did not previously exist as a command).
- Tests: `tests/unit/sync/test_Vault__Ignore.py`,
  `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py` (vault-level regression).

**Acceptance**
- [ ] **Tracked-wins.** A vault whose head tracks `.github/workflows/x.yml` still has that
      file in the head after an upgrade + `sgit push` with no other changes — and `sgit push`
      reports **nothing to push**, not a deletion.
- [ ] **Fresh vaults.** In a vault created after this change, `.github/**` is never added by
      `sgit push`, and `sgit status` lists it as ignored with `.github` as the reason.
- [ ] **Deliberate removal is still possible** — the escape hatch is named in the migration
      notice and does what it says (one visible commit, not a silent drop).
- [ ] **Migration notice.** The first run against a vault whose head tracks `.github/**`
      says so plainly and names the choice (keep tracking, or remove deliberately). Once, not
      on every command.
- [ ] **No behaviour change for every other ignore rule** — the existing ignore suite passes
      untouched. Tracked-wins is general (it is git's rule), so state in the docs that it now
      applies to all rules, not just `.github`.
- [ ] `.github` is documented in the user-facing ignore list alongside `.git`, `.sg_vault`,
      `node_modules`.

**Why it is P0 rather than a footnote in P1:** the maintainer's acceptance of the AppSec
findings was conditional on *"no side effects on existing vaults and sgit functionality"*.
This phase is that condition. Rationale and the verified code references:
[`12__accepted-risks.md`](12__accepted-risks.md) §6.

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
- [ ] **SP-1 (AppSec, must-fix):** every fetched `obj-cas-imm-*` object is id-verified
      `sha256(ciphertext)[:12] == id` **before it is written** — the shipped clone path skips
      this today (`Clone__Workspace.save_file` writes unchecked; `verify_integrity` exists but
      no clone step calls it). Per-object failure, not per-run. This makes `00` §3 / `03` §2
      true instead of aspirational.
- [ ] **Only an HTTP 404** is `None` (absent); connection refused/reset/timeout **raises
      loudly, naming the host** — a dead host must never diagnose as an empty vault
      ("no branch index and no named ref"), which sends operators toward re-keying
      instead of restarting a server (tabletop `11`, F5).
- [ ] Per-object failures never abort the run.
- [ ] Resolved transport appears in `sgit vault info`.
- [ ] **SP-6 (CLI half):** cloning a **private** read key over a plain `http://` base URL
      warns loudly (the key is in argv and the transport is unauthenticated/observable);
      `sgit_public_read_` is exempt — it is already public. The loader-side half (fragment
      hygiene: no Referer, no history, no redirect carry-over) is the Web team's, `01` §7.

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
- `sgit_ai/core/serve/Vault__Static_Server.py` — stdlib `ThreadingHTTPServer`,
  read-only, no directory listing, path-guarded with `Vault__Path_Guard`.
  *(r15: moved from the originally-specified `network/serve/` — the repo's layer rules
  forbid network → storage imports and the path guard lives in storage; core imports both.)*
- `sgit_ai/cli/CLI__Serve.py`; wire in `CLI__Main.py`.
- Tests: `tests/unit/core/serve/test_Vault__Static_Server.py`.

**Acceptance**
- [ ] Serves the surface at `/` and **routes** `/api/vault/read/<vid>/bare/*` to
      `.sg_vault/bare/*` (virtual composition — no copies); GETs return byte-identical
      content (I1).
- [ ] **SP-8 (must-fix):** the virtual route resolves through `Vault__Path_Guard` — a request
      for `…/bare/../../../etc/passwd` (and encoded variants) is refused, not served.
- [ ] **SP-9:** the server validates the `Host` header against `127.0.0.1`/`localhost` (DNS-
      rebinding defence), and `--bind 0.0.0.0` prints a sharp warning that the vault is exposed
      to the LAN read-key-free.
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

## P9 — `sgit vault attach` (small, CI-blocking)

A fresh `git clone` of a one-repo vault has `.sg_vault/bare/` but no `local/` — and no
shipped command can bind a key to it. **Executed evidence (19 Aug):** `clone-headless`
refuses inside a vault; `sgit status` errors "vault may be corrupted"; tabletop 10 step 9
recovered with a lab script, which is the definition of a missing command.

**Acceptance**
- [ ] **SP-4 (decision before CI is "supported"):** the one-repo pattern lets a vault-write
      collaborator ship reader-facing HTML through vault→work-tree→repo. The workflow-file
      half of this is **closed by decision 17 / P0** — `.github/` is no longer vault content,
      so vault-write no longer ships workflow files at all. What remains is the HTML half, and
      the runner hardening below. The CI story is not promoted from tabletop to supported until the
      runner is least-privilege (SP-10: SHA-pinned actions, pinned sgit, `persist-credentials:
      false`, no `pull_request_target`) and the docs state plainly that one-repo vault-write
      grants runner code execution — which, for a private vault, reaches `SGIT_READ_KEY`.
- [ ] `sgit vault attach <vault-key | read-key + vault-id>` writes `local/` (config, key,
      derived ids) against the **existing** `bare/`, validating that the derived ref file id
      exists in `bare/refs/` before writing anything.
- [ ] Works with a read key alone → read-only clone semantics (no write credential stored).
- [ ] Refuses a key whose derived ids match nothing in `bare/` (wrong key, clear message).
- [ ] After attach: `sgit status`, `sgit publish`, `sgit vault serve` all work.
- [ ] Attach is **mode-exclusive**: switching read-only ↔ read-write removes the other
      mode's artifacts, and `clone_mode.json` is written **Schema__Clone_Mode-exact** — the
      shipped clone-mode guard refuses anything else, correctly (tabletop `11`, F6).
- [ ] The tabletop lab script `ci_publish_readkey.py` is retired by it (11 step 2).

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
- [ ] **SP-7:** `vault info` / publish output carries the dropped-properties note — a static
      target has **no server-side revocation, no auth, no read audit** that the live API had;
      "bare" means unlisted, **not** access-controlled.
- [ ] **SP-12:** at `--visibility bare`, one line notes that `manifest.json` still discloses
      estate shape (object count, sizes, commit cadence) — required for custody, disclosed on
      purpose.

---

## P4b — Published API docs

Full design and acceptance criteria: [`08__api-docs.md`](08__api-docs.md).

**Files:** `sgit_ai/core/actions/publish/Vault__Publish__Api_Docs.py`;
`Schema__OpenAPI_Document.py`; `Enum__Api_Docs_Mode.py` (`CDN | BUNDLED`);
`sgit_ai/network/assets/Swagger_UI__Assets.py` (fetch-verify-cache, bundled mode only).

**Acceptance:** the checklist in `08` §7, plus **SP-11: the CSP `<meta>` is mandatory, not
"belt and braces"** — `script-src` limited to self + the pinned CDN, and `connect-src 'self'`
as the exfiltration backstop on any page that shares an origin with the loader. Three more
that are easy to miss: `servers` must be
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
- [ ] **SP-3 (must-fix):** for `obj-cas-imm-*` objects the mirror **recomputes the id and
      ignores the manifest `sha256`** — the manifest is self-attested by the same host, so its
      hash is not an authority; the content-address is. Refs/indexes/keys (not
      content-addressed) fall back to the manifest `sha256` and are flagged as
      host-attested-only in the output.
- [ ] **SP-8 (must-fix):** every manifest `file_id` is routed through `Vault__Path_Guard`
      before being used as a write path — a `file_id` of `../../etc/cron.d/x` is refused.
      Bound the object count and total size against the manifest; reject duplicate/conflicting
      `file_id` entries.
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
