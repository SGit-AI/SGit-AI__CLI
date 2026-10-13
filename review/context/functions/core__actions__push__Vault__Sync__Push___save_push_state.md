## `_save_push_state` / `_clear_push_state` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L753-L763)

**Purpose:** Persist the checkpoint (`json.dump(state.json())`, then `chmod 0600`, errors ignored L756-L759); remove it when the push completes (L761-L763).

**Inputs & Assumptions:** `path`, `state`. Written with `open(path, 'w')` then chmod — not through `Vault__Secret_File` (the single secret writer the threat model names for keys); the content is object ids and the remote URL, not key material.

**Outputs & Effects:** local file; no network. `push` saves after each large blob (L294) and after the small-blob batch (L318); clears at L389 only on the non-first-push path.

**Cross-Function Dependencies:** callers `push` L294, L318, L389. Test: `test_save_push_state_chmod_error_silenced_lines_375_376`. (`Vault__Sync__Base._clear_push_state` L594-L596 is a duplicate definition; the subclass's wins.)

**Open Questions:** none.
