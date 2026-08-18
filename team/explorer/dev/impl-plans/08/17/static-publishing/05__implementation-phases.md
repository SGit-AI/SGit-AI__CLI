# 05 — Implementation Phases

Each phase is independently shippable: one PR, green suites, its own acceptance criteria.
**Start with P1 and P3** — together they are demonstrable value and commit to nothing in
the publish protocol that is still under discussion.

| Phase | Deliverable | Depends on | Size | Risk |
|---|---|---|---|---|
| P1 | Static read transport, productionised | — | S | low |
| P2 | `sgit publish` (ciphertext only) + `manifest.json` | P1 | M | **medium** |
| P3 | `sgit vault serve` | — | S | low |
| P4 | `--visibility`, cover, invariant-5 enforcement | P2 | M | **medium** |
| P5 | `sgit vault mirror` (custody) | P2 | S | low |
| P6 | Bundles | P2 | M | low |
| P7 | Invariants + 14 cells as a suite | P1–P5 | M | — |

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

## P2 — `sgit publish` (ciphertext only) + `manifest.json`

**Files**
- `sgit_ai/core/actions/publish/Vault__Publish.py`
- `sgit_ai/schemas/publish/Schema__Published_Manifest.py`,
  `Schema__Published_Object.py`, `Schema__Plaintext_Entry.py`
- `sgit_ai/safe_types/Enum__Published_Layout.py` (`API_PATH | FLAT`),
  `Enum__Visibility.py` (`BARE | NAMED | PUBLIC` — used fully in P4)
- `sgit_ai/cli/CLI__Publish.py`; wire in `CLI__Main.py`
- Tests: `tests/unit/core/actions/publish/…`, `tests/unit/schemas/publish/…`

**Acceptance**
- [ ] Ciphertext in the output is **byte-identical** to `.sg_vault/bare/…` (I1).
- [ ] `manifest.json` lists every object with size, the ordered commit list (walked from the
      head **via parents** — walking a commit log misses the init commit's empty trees), the
      head, and the hashed plaintext surface.
- [ ] The plaintext surface comes from a **fixed allow-list in code**; a test asserts a vault
      file named `index.html` does **not** get emitted as plaintext.
- [ ] Every schema round-trips (`from_json(x.json()).json() == x.json()`).
- [ ] Publishing the same vault twice produces identical bytes (deterministic).

**Risk:** this phase owns the plaintext boundary. If in doubt, emit less.

---

## P3 — `sgit vault serve`

**Files**
- `sgit_ai/network/serve/Vault__Static_Server.py` — stdlib `ThreadingHTTPServer`,
  read-only, no directory listing, path-guarded with `Vault__Path_Guard`.
- `sgit_ai/cli/CLI__Serve.py`; wire in `CLI__Main.py`.
- Tests: `tests/unit/network/serve/test_Vault__Static_Server.py`.

**Acceptance**
- [ ] Serves a published folder; GETs return byte-identical content.
- [ ] Binds `127.0.0.1` by default; `--bind` widens and says so loudly.
- [ ] Path traversal is impossible — `GET /../../etc/passwd` and encoded variants refused
      (reuse the existing traversal test payloads).
- [ ] No writes: any non-GET/HEAD returns 405.
- [ ] `--port 0` picks a free port and prints it (needed by tests).
- [ ] Run inside a vault with no argument → publishes to a temp dir, serves it, cleans up.
- [ ] Help text explains **why** the command exists (the opaque-origin rule).

**Watch out:** no new dependency. The product's claim is that no server is needed; this one
is a local convenience and must look like it.

---

## P4 — Visibility, cover, and invariant-5 enforcement

**Files**
- `sgit_ai/schemas/publish/Schema__Vault_Cover.py` (`title`, `description`, `image`,
  `updated`, `access`, `public`)
- visibility recorded in the vault (local config or a vault file — see decision 5)
- `Vault__Publish` — emit `sgit_public_read_<hex>` only when `PUBLIC`; the confirmation
  prompt; the `--with-plaintext` refusal; the git-history note.

**Acceptance**
- [ ] `--with-plaintext` without `--visibility public` exits non-zero and **writes nothing**
      (assert the output dir is untouched).
- [ ] `--visibility public` prompts unless `--yes`, and the prompt states irreversibility.
- [ ] The published key file uses `format_read_key(hex, public=True)` →
      `sgit_public_read_<hex>`.
- [ ] Visibility is **recorded**, so a republish cannot silently flip private → public by
      inheriting a different default.
- [ ] Git-hosted output prints the history note.
- [ ] `sgit_private_*` can never appear as a published filename — assert it.

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

See `04__invariants-and-tests.md`. Build the five invariants first — they cover the most
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
