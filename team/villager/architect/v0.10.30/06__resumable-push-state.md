# Finding 06 — Resumable push state

**Verdict:** `BOUNDARY OK` for the design, but **MEDIUM-severity edge cases**
in the cleanup path. **No SEND-BACK-TO-EXPLORER** required.

---

## 1. State machine

`push_state.json` lives at `.sg_vault/local/push_state.json`. The state
machine has three transitions:

```
[no file]  ──first blob upload──▶  [present, blobs_uploaded=[b1]]
                                         │
                                         ├─more blobs─▶ [present, blobs_uploaded=[b1, b2, ...]]
                                         │
                                         └─Phase B success──▶  [no file]
```

Code paths (with line refs):
- Created/appended: `Vault__Sync.push` lines 962–1018.
- Cleared: `Vault__Sync.push` line 1068, via `_clear_push_state`.
- Read on resume: `_load_push_state` lines 2729–2740.

The composite identity is `(vault_id, clone_commit_id)`. If either differs
from the in-flight push, `_load_push_state` returns a fresh empty state and
**the on-disk file is silently overwritten** by the next `_save_push_state`
call. That's safer than aborting (no orphan files), but it does mean a
race-condition between two pushes for the same directory is undefined —
unlikely in practice (single-user CLI), worth flagging.

## 2. Cleanup edge cases

### 2a. CAS conflict — checkpoint NOT cleared (correct)

If Phase B fails with a CAS conflict (someone else pushed in the meantime),
the checkpoint persists. The next `sgit push` re-loads the same blob list,
sees they're already uploaded, and skips Phase A. **Correct per debrief 03.**

This is verified in `push()` flow only by the absence of `_clear_push_state`
on the failure path (line 1068 only runs after Phase B success).

### 2b. User runs `sgit reset` between pushes — orphan checkpoint

If a user pushes `commit_A` partway, then runs `sgit reset --hard commit_B`,
the next `sgit push` will:
1. `_load_push_state` checks `clone_commit_id` — it's `commit_A`, not the new
   `commit_B`, so it **discards the checkpoint** (returns fresh state).
2. The blob upload IDs from the previous attempt are forgotten, and the new
   push will re-upload any blobs unique to `commit_A` that are also needed
   for `commit_B`.

The blobs are CAS-deduplicated server-side, so this is a wasted
*round-trip*, not a wasted *upload*. **Acceptable behaviour, but the
checkpoint file is now an orphan that will be overwritten by the next
successful push.** Cleanup is implicit, not explicit.

If we want clean teardown semantics, `sgit reset` could call
`_clear_push_state` itself. This is a polish improvement, not a bug.

### 2c. User runs `sgit rekey` mid-push — orphan checkpoint

`rekey_wipe` does `shutil.rmtree(.sg_vault/)`, which **also removes
push_state.json** (it lives under `.sg_vault/local/`). So rekey naturally
cleans up. No bug here, but worth confirming via a test.

### 2d. User runs `sgit delete-on-remote` — checkpoint orphan on server-side delete

`delete_on_remote` only touches the server. The local `push_state.json`
persists. The next push will load it, see `clone_commit_id` matches the
local clone branch, attempt to skip Phase A blobs — but **those blobs are
gone from the server because of `delete_on_remote`**. Phase B will succeed
in re-uploading commit/tree/ref data, but the blobs themselves will be
missing on the server.

Wait, let me re-check: `build_push_operations(named_blob_ids=uploaded_blob_ids)`
treats `uploaded_blob_ids` as "blobs already on server" — so they're SKIPPED
from the Phase B operations. Result: server has commits and trees pointing
at blobs that don't exist there. **This is a correctness bug.**

Mitigations:
- The `delete_on_remote` CLI flow tells the user "next: sgit rekey", which
  will wipe `push_state.json` via rmtree.
- If the user manually pushes after delete-on-remote without rekey, they hit
  the bug.

**Recommendation:** `delete_on_remote` should also call `_clear_push_state`
locally. Single-line fix, but Architect-level enough to flag rather than
silently address.

### 2e. Schema absence (cross-ref to finding 05)

No `Schema__Push_State` exists. The dict shape is implicit. A stale
`push_state.json` with an unexpected schema (e.g. older sgit version) is
handled by the `try: ... except: pass` at line 2737 — falls back to fresh
state. This is defensive enough that the lack of schema is operationally
safe, but it's still a Type_Safe rule violation.

## 3. Forward compatibility

The dict has three keys today (`vault_id`, `clone_commit_id`, `blobs_uploaded`).
A future version that adds e.g. `trees_uploaded` will be silently dropped on
read by an older client (because there's no schema, and `state.get(...)`
ignores extras). Forward-compat is fine, but you can't tell from code review —
no schema means no contract.

## 4. Hand-off

- **Dev (Phase 3):** add `_clear_push_state` to the `delete_on_remote` flow.
  One line, one new test asserting `not os.path.isfile(push_state_path)`
  after delete.
- **Dev (Phase 3, lower priority):** consider `_clear_push_state` from
  `reset` for cleanliness. Also a one-liner.
- **AppSec/QA:** the test plan needs:
  - "push_state.json survives Phase A failure, gets reused on retry"
  - "push_state.json discarded when clone_commit_id changes (after reset)"
  - "delete_on_remote followed by push does not leave server in a half-state"
- **Architect (cross-ref to finding 05):** add `Schema__Push_State`.

---

## 5. Closeout — Brief 14 (2026-05-01)

**Status: CLOSED.**

Fix applied in `sgit_ai/sync/Vault__Sync.py` — `delete_on_remote` now calls
`_clear_push_state(storage.push_state_path(directory))` after
`api.delete_vault()` and `crypto.clear_kdf_cache()` (three-line addition,
no behaviour change for any other path).

Test coverage in `tests/unit/sync/test_Vault__Sync__Delete_Push_State.py`
(4 tests):

| Test | Purpose |
|---|---|
| `test_bug_stale_push_state_exists_before_delete` | Precondition: stale push_state.json can exist before delete |
| `test_delete_on_remote_clears_push_state` | Fix verification: push_state.json absent after delete_on_remote |
| `test_delete_on_remote_clears_push_state_even_when_no_prior_push` | Safety: no error when push_state.json absent |
| `test_repush_after_delete_uploads_blobs_fresh` | End-to-end: re-push after delete uploads blobs (objects_uploaded > 0) |

Suite result after fix: **2149 passed** (4 new tests, 0 regressions).
