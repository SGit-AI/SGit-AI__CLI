# Brief 12 — Vault move cleanup pass (post-review follow-ups)

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands first in the remaining v0.14.x work — addresses follow-ups from the brief 02 implementation review (`11__implementation-review.md`). Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

The brief 02 (vault move) implementation landed cleanly and the v0.14.x release of `vault backup` + `vault move` was greenlit. This brief addresses three minor follow-ups flagged in the implementation review — all 🟡 (non-blocking, but worth tightening before they accumulate):

1. **Silent re-encryption fallbacks** — 7 sites in `Step__Move__Build_Temp_Vault` swallow exceptions and fall back to writing the old ciphertext into the new vault. Same family of pattern we hardened in `Migration__Tree_IV_Determinism`. Apply the same treatment.
2. **`store_at()` bypassed** — the brief introduced `Vault__Object_Store.store_at()` for the move code path, but `Build_Temp_Vault` writes via raw `open()`. Refactor to use the abstraction so future invariants on `store_at` apply.
3. **Cleanup state detection edge case** — verify `--cleanup` correctly handles the post-8a, pre-8b state (atomic rename done locally; server delete pending). Likely covered by existing tests; if not, add the missing case.

---

## 2. Item 1 — Surface re-encryption failures, don't silently fallback

### 2a. The pattern to fix

`sgit_ai/workflow/move/steps/Step__Move__Build_Temp_Vault.py` has 7 sites with this shape:

```python
try:
    plaintext  = crypto.decrypt(old_key, old_cipher)
    plaintext  = self._reencrypt_inner_fields(plaintext, old_key, new_key, crypto)
    new_cipher = crypto.encrypt(new_key, plaintext)
except Exception:
    new_cipher = old_cipher    # ← silent: write the old (unreadable-by-new-key) bytes
```

The seven sites:
- `_reencrypt_objects` line ~118 — main object loop
- `_reencrypt_inner_fields` line ~140 (tree fields), line ~148 (commit message_enc)
- `_migrate_refs_and_index` line ~171 (refs), line ~189 (index)
- `_reencrypt_keys` line ~217

### 2b. Why this is dangerous

If a single object fails to decrypt under the old key (e.g. corrupt ciphertext, key derivation bug), the move silently writes the ORIGINAL ciphertext into the new vault. The new vault then has one object encrypted with the OLD key — unreadable by the new key. The user won't know until they later try to read that specific object via `clone`/`pull`/`history show`, at which point the failure surfaces with no link back to the move that introduced the corruption.

This is the same family of issue we hardened in `Migration__Tree_IV_Determinism` (briefs 00c review, B02 hardening pass). Apply the same fix here.

### 2c. The fix

Split the exception handling into two cases:

```python
except (FileNotFoundError, OSError):
    pass    # legitimate: object missing locally (sparse clone) — skip silently
except Exception as e:
    raise RuntimeError(
        f'vault-move: failed to re-encrypt object {fname!r}: {e}. '
        f'Move aborted — local clone is unchanged. '
        f'.sg_vault_new/ may be partially built; remove it before retrying.'
    ) from e
```

For the 7 sites, the message should name the failing artefact:
- Object loop → object filename
- Tree fields → field name + tree object id
- Commit message → commit object id
- Refs → ref filename
- Index → index file id
- Keys → key file name

The behavioural contract: if step 3 (`Build_Temp_Vault`) raises, the user's working `.sg_vault/` is untouched, `.sg_vault_new/` may exist in a partial state and should be removed before retry. The error message should say so.

### 2d. Tests

In `tests/unit/core/actions/move/test_Vault__Sync__Move__Build_Temp_Vault__Errors.py` (new):

1. `test_corrupt_object_aborts_move_with_clear_error` — set up a vault, corrupt one `bare/data/<id>` file (write garbage bytes), run move, assert `RuntimeError` raised with the failing object id in the message.
2. `test_corrupt_tree_inner_field_aborts_with_field_name` — same idea but corrupt a tree's `name_enc` value, assert the error names the field.
3. `test_corrupt_ref_aborts` — corrupt a ref file.
4. `test_missing_object_during_sparse_clone_does_not_abort` — set up a sparse clone where some objects aren't local, run move, assert it succeeds with the missing objects skipped (no `RuntimeError`).
5. `test_partial_temp_vault_left_on_failure` — after the abort, assert `.sg_vault_new/` exists but `.sg_vault/` is byte-identical to pre-move snapshot.
6. `test_partial_temp_vault_removable_via_cleanup` — same setup, run `sgit vault move --cleanup`, assert the temp folder is removed.

---

## 3. Item 2 — Use `store_at()` in the move code path

### 3a. The bypass

`Step__Move__Build_Temp_Vault.py:120` writes via raw file I/O:

```python
with open(os.path.join(new_data_dir, fname), 'wb') as f:
    f.write(new_cipher)
```

Brief 02 §5a explicitly introduced `Vault__Object_Store.store_at(object_id, content, force=False)` for this exact code path. The unused `new_obj_store` parameter (lines 56, 103) is a dead giveaway — it's constructed but never called.

### 3b. The fix

Refactor `_reencrypt_objects` to use the API:

```python
def _reencrypt_objects(self, sg_dir, new_sg_dir, old_key, new_key, crypto, new_obj_store):
    data_dir = os.path.join(sg_dir, 'bare', 'data')
    if not os.path.isdir(data_dir):
        return
    for fname in os.listdir(data_dir):
        if not fname.startswith('obj-cas-imm-'):
            continue
        with open(os.path.join(data_dir, fname), 'rb') as f:
            old_cipher = f.read()
        try:
            plaintext  = crypto.decrypt(old_key, old_cipher)
            plaintext  = self._reencrypt_inner_fields(plaintext, old_key, new_key, crypto)
            new_cipher = crypto.encrypt(new_key, plaintext)
        except (FileNotFoundError, OSError):
            continue
        except Exception as e:
            raise RuntimeError(...) from e

        new_obj_store.store_at(object_id=fname, content=new_cipher, force=True)
```

Same treatment for refs and indexes — call the appropriate `Vault__Ref_Manager` / `Vault__Branch_Manager` write APIs if they exist, otherwise leave the raw I/O for those (they're not object-store paths).

### 3c. Tests

The existing `test_Vault__Sync__Move__Object_IDs.py` tests already verify that filenames are preserved end-to-end, so they'll continue to pass. Add a focused test:

7. `test_build_temp_vault_uses_store_at` — instrument `Vault__Object_Store.store_at` (e.g. via a thin wrapper subclass injected through dependency injection if the test framework allows, OR via counting how many `store_at` calls happened by checking the resulting file structure). Assert it was called for every `obj-cas-imm-*` file in the source.

If instrumentation is too invasive, skip this test and trust the refactor was done — the existing object-id stability tests provide indirect coverage.

---

## 4. Item 3 — Cleanup state detection between 8a and 8b

### 4a. The state to verify

After step 8a (atomic local rename) succeeds but before step 8b (server delete) runs:
- `.sg_vault/` now contains the NEW vault (rename completed).
- `.sg_vault_old_<ts>/` exists with the old vault content.
- The old vault is still live on the source server (delete hasn't run).

If the user Ctrl+Cs at this exact moment, they need `sgit vault move --cleanup` to:
- Detect the state (no `.sg_vault_new/`, but old vault still exists on server based on move-history).
- Run the server delete (8b).
- Remove `.sg_vault_old_<ts>/`.

### 4b. Verify the existing test covers this

Read `tests/unit/core/actions/move/test_Vault__Sync__Move__Cleanup.py::test_cleanup_finishes_server_delete_after_8b_failure`. Confirm:
- The test sets up the post-8a-pre-8b state correctly.
- Cleanup detects it via the move-history record (last record's `to_vault_id` matches local config's `vault_id` AND `from_vault_id` is still readable on the source server).
- Cleanup completes 8b and removes the `.sg_vault_old_<ts>/` directory.

### 4c. Add coverage if missing

If the existing test doesn't cover this exact scenario:

8. `test_cleanup_after_atomic_rename_completes_server_delete` — after 8a succeeds, before 8b runs (use a `Vault__API` subclass that fails the first `tombstone_vault` call), trigger `sgit vault move`. Confirm partial state: new local + old on source. Run `sgit vault move --cleanup`. Assert: server delete completes, old vault tombstoned, `.sg_vault_old_*` cleaned.

If the existing test does cover this — no new test needed; just the spot-check.

---

## 5. Out of scope

- **Refactoring all of `Build_Temp_Vault` for symmetry** — only address the three follow-ups. Other style cleanup waits for Reviewer Fix passes.
- **Adding telemetry / progress callbacks to the move workflow** — separate brief if desired.
- **Backwards compatibility for half-moved vaults from before this brief** — n/a, vault move shipped today; no pre-existing partial states exist.

---

## 6. Verification checklist

When done:

- All ~6-8 new tests pass.
- The existing 3,418-test suite still passes.
- A deliberately-corrupted `bare/data/*` file causes the move to abort with a clear error naming the corrupt object — instead of silently producing a half-broken new vault.
- `Vault__Object_Store.store_at()` is invoked from the move code path (verifiable via grep).
- `sgit vault move --cleanup` correctly handles the post-8a-pre-8b state.
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~½ day total (item 1 fix + tests ~2.5h, item 2 refactor + test ~1h, item 3 spot-check or new test ~1h, reviewer fix pass ~30min).
