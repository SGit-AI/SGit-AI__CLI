# Brief B15 — Generalise: Push / Pull / Fetch

**Owner role:** **Villager Dev** (Architect-blessed for shared-step refactor)
**Status:** BLOCKED until B06 + B08 + B13 land.
**Prerequisites:** B06 (workflow on clone), B08 (server packs), B13 (Core+Network restructure).
**Estimated effort:** ~4–6 days
**Touches:** the now-extracted `sgit_ai/core/actions/{push,pull,fetch}/` modules from B13; new shared step library under `sgit_ai/core/shared/`; server-side push-pack support; tests.

---

## Why this brief exists

Once `clone` is workflow-driven (B06) and uses server packs (B08), the
same approach applies to `push`, `pull`, `fetch`. They share a lot of
step types — `walk_commits`, `walk_trees`, `download_blobs`,
`upload_blobs` — which become a **shared step library**.

Server-side: push needs an inverse of clone packs — clients can upload
a single binary "push pack" containing new objects; server unpacks.

---

## Required reading

1. This brief.
2. `design__04__workflow-framework.md` — shared step library policy.
3. `design__05__clone-pack-format.md` — pack design (now bidirectional).
4. The implementations of B05, B06, B08.
5. Existing `Vault__Sync.push`, `Vault__Sync.pull`, `Vault__Sync.fetch`.
6. The v0.10.30 resumable-push design at
   `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/03__resumable-push-blob-checkpointing.md`
   — push already has step-like state. This brief turns it into a real workflow.

---

## Scope

### Step 1 — Shared step library

Refactor B06's clone-specific steps into a shared library where appropriate:

| Step | Used by |
|---|---|
| `derive_keys` | clone, push, pull, fetch |
| `download_index` | clone, pull, fetch |
| `download_branch_meta` | clone, pull, fetch |
| `walk_commits` | clone, pull, fetch |
| `walk_trees` | clone, pull, fetch |
| `download_blobs` | clone, pull |
| `upload_blobs` (NEW) | push |
| `download_pack` | clone, pull |
| `upload_pack` (NEW) | push |
| `merge` (NEW) | pull |
| `fast_forward_check` (NEW) | push, pull |

Move shared classes into `sgit_ai/core/shared_steps/` (post-B13 layout). Per-command-only
classes stay under `sgit_ai/workflow/<command>/`.

### Step 2 — `Workflow__Push`

Refactor `push` into a workflow. Builds on the v0.10.30 resumable-push
checkpoint state — that becomes the workflow workspace.

Steps (sketch):
1. `derive_keys`
2. `local_state_inventory` — what commits/trees/blobs are local-only?
3. `negotiate_with_server` — ask server "what do you have?", produce a list of objects to upload.
4. `build_upload_pack` — assemble local objects into an upload pack.
5. `upload_pack` — POST to `POST /vaults/{id}/packs/upload`.
6. `update_remote_ref` — write the new HEAD ref.
7. `clear_workspace` — clean up.

### Step 3 — `Workflow__Pull`

Refactor `pull` into a workflow:
1. `derive_keys`
2. `download_index`
3. `download_branch_meta`
4. `walk_commits`
5. `negotiate_with_server` — what do we already have?
6. `download_pack` — only new objects (delta pack flavour or per-object).
7. `merge` — fast-forward or three-way.
8. `update_local_ref`.

### Step 4 — `Workflow__Fetch`

Subset of pull: stops before the merge.

### Step 5 — Server-side push pack

`POST /vaults/{vault_id}/packs/upload` accepts a binary push-pack:
- Header (magic + version + claimed HEAD commit-id).
- Index + body (same wire format as clone packs from B08, just inverse direction).
- Server validates ciphertext, writes to per-object storage, optionally
  triggers post-push pack pre-build for clone consumers.

### Step 6 — Tests

- One workflow-level happy-path test per command (push/pull/fetch).
- Resumable push: interrupt mid-upload, resume, verify identical end state.
- Pack upload: server receives + unpacks correctly.
- Fast-forward + three-way merge tests for pull.
- Performance regression: push the case-study vault end-to-end, baseline + post-pack.

---

## Hard constraints

- **Behaviour preservation** for the public push/pull/fetch APIs (CLI invocations + return shapes).
- **Type_Safe everywhere.**
- **No mocks.**
- **No `__init__.py` under `tests/`.**
- **Resumability** — `sgit dev workflow resume` must work for interrupted push/pull/fetch.
- Coverage on new code ≥ 85%.
- Suite must pass under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Shared step library exists at `sgit_ai/core/shared_steps/`.
- [ ] `Workflow__Push`, `Workflow__Pull`, `Workflow__Fetch` implemented.
- [ ] Server-side `POST /packs/upload` endpoint shipped + tested.
- [ ] Resumable push works via the workflow framework (replaces the v0.10.30 ad-hoc `push_state.json` mechanism).
- [ ] All existing push/pull/fetch tests pass without modification.
- [ ] Performance regression: case-study push improvement vs baseline (target informed by B07 numbers).
- [ ] At least 8 new workflow-level tests.
- [ ] Coverage on new code ≥ 85%.
- [ ] Suite ≥ existing test count + N passing.

---

## Out of scope

- Re-architecting merge semantics. The `merge` step uses the existing
  three-way merge logic; refactor into a step is mechanical.
- New CLI commands. Pull/push/fetch keep their top-level surface.
- Distributed / multi-replica coordination.
- The v0.10.30 `push_state.json` schema migration — that's v0.10.30
  brief 15. This brief migrates the runtime to the workflow workspace
  but tolerates the old schema for one release (the shape is
  load-bearing for old in-flight pushes).

---

## Deliverables

1. Shared step library under `sgit_ai/core/shared_steps/`.
2. `Workflow__Push`, `Workflow__Pull`, `Workflow__Fetch`.
3. Refactored `push`, `pull`, `fetch` methods in `Vault__Sync.py`.
4. Server-side push-pack endpoint.
5. Tests.
6. Closeout note in sprint overview.

---

## When done

Return a ≤ 350-word summary:
1. Workflow shapes (step lists per command).
2. Shared-library size + which workflows use which steps.
3. Resumable-push replacement: confirmed working via framework.
4. Performance numbers per command vs baseline.
5. Coverage + test count deltas.
6. Anything that surfaced about pack design that needs B08 follow-up.
