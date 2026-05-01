# Brief 14 — Bug fix: `delete-on-remote` leaves stale push_state

**Owner role:** **Villager Dev**
**Status:** Ready to execute. **This is a real bug, not just hardening.**
**Prerequisites:** None.
**Estimated effort:** ~2 hours (one-line fix + tests proving the failure
mode and the fix)
**Touches:** `sgit_ai/sync/Vault__Sync.py` (`delete_on_remote`,
`_clear_push_state`), tests under `tests/unit/sync/`.

---

## Why this brief exists

Architect finding 06 surfaced this during the deep-analysis review:

`delete-on-remote` followed by `push` (without `rekey` between) leaves
`push_state.json` in place. The next push will skip Phase-A blob uploads
thinking they're on the server, while Phase-B uploads commits/trees
that point at deleted blobs. **Result: server holds dangling references
to blobs that were deleted.**

Severity: **MEDIUM** (data integrity; user-visible failure mode).

The fix is small (call `_clear_push_state` inside `delete_on_remote`),
but the **tests are the substantive deliverable**: they document the
bug as a passing test that fails before the fix and passes after.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/06__resumable-push-state.md` —
   the finding.
3. `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/03__resumable-push-blob-checkpointing.md`
   — the resumable-push design.
4. `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/05__probe-delete-rekey-vault-lifecycle.md`
   — the delete-on-remote design.
5. `sgit_ai/sync/Vault__Sync.py` — `delete_on_remote` method and the
   `_load_push_state` / `_save_push_state` / `_clear_push_state` triplet
   (~line 2729–2748 per Dev finding 09).

---

## Scope

**In scope:**
- Add `self._clear_push_state(...)` (or equivalent) inside
  `delete_on_remote` so the push checkpoint is wiped when the vault
  it tracked is destroyed remotely. Place it where it cannot be
  skipped on a partial-failure path.
- Tests **first**, in this order:
  1. **Bug-reproduction test** (passing on current `dev`): a vault is
     pushed, the push leaves `push_state.json`, then `delete_on_remote`
     is called, `push_state.json` still exists. **This test passes
     before the fix; it confirms the bug.**
  2. **Fix-verification test** (failing before, passing after):
     `push_state.json` is gone after `delete_on_remote` returns
     successfully.
  3. **End-to-end test**: push → delete-on-remote → re-push to the
     SAME vault id → blobs are uploaded fresh (Phase A is not skipped).
     This is the user-visible failure mode the bug causes.
- Update `team/villager/architect/v0.10.30/06__resumable-push-state.md`
  with a closeout note.

**Out of scope:**
- Changing the resumable-push design itself.
- Schema for `push_state.json` — that's brief 15.

**Hard rules:**
- No mocks; use the real in-memory transfer server.
- Tests under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Bug-reproduction test exists and passes on the `dev` HEAD before
      your fix lands. (Verify by checking out `dev` momentarily, running
      it, then returning to your branch — or by running it before
      committing the source fix.)
- [ ] Fix-verification test fails before the fix and passes after.
- [ ] End-to-end test passes.
- [ ] Suite ≥ 2,105 passing.
- [ ] Coverage delta: should INCREASE (this brief covers previously
      0%-coverage paths in `_clear_push_state` and the `push_state.json`
      lifecycle).
- [ ] No new mocks.
- [ ] Closeout note appended to Architect finding 06.

---

## Deliverables

1. Source change in `delete_on_remote` (the one-line fix).
2. Test file (e.g.,
   `tests/unit/sync/test_Vault__Sync__Delete_Push_State.py`).
3. Closeout note on Architect finding 06.

Commit message:
```
fix: clear push_state on delete-on-remote

Closes Architect finding 06 (v0.10.30 review). delete-on-remote left
push_state.json intact, causing the next push to a fresh vault of the
same id to skip Phase-A blob upload and produce dangling references
in Phase-B commit/tree uploads.

The fix is one line; the substance is the tests, which document the
bug as a passing reproduction and verify the resolution end-to-end
against the in-memory transfer server.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Source fix location (file:line).
2. Test count + names.
3. Coverage delta on `Vault__Sync.py` push-state triplet (should now be
   100% covered).
4. Whether the bug-reproduction test was confirmed passing on `dev`
   HEAD before the fix.
