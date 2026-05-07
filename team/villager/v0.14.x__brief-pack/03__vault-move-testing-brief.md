# Testing Brief — `sgit vault move` (multi-round, transactional, regression)

**Date:** 2026-05-06
**Audience:** Sonnet executor + QA (alongside the implementation brief `00h`)
**Scheduling:** ships with `00h`. Tests are not optional — they're a hard prerequisite for merge.
**Author:** Villager orchestrator (Opus)

---

## 1. Why a separate testing brief

`sgit vault move` is the single most destructive operation we ship. The user's vault is at stake. A bug here doesn't just inconvenience — it can permanently lose plaintext data. The test surface is meaningfully larger than for any other command because:

1. **Multi-round moves** must be tested. A user may rotate a key, then later move servers, then later rotate again. Tests must cover at least 3 sequential moves with verification between each.
2. **Object-ID stability** is the design contract. Every test must capture pre/post object-ID sets and assert what should/shouldn't have changed.
3. **Transactional integrity** is the design contract. Every step must have a failure-injection test demonstrating zero data loss before the destructive boundary at step 7.
4. **All key downstream operations** (clone, commit, push, pull, fetch, history log, history reset, share, migrate) must continue to work on the moved vault — and on the moved-then-re-moved vault.

The implementation brief lists 9 mandatory tests. This brief expands that into a comprehensive matrix and adds the qa-tier multi-round scenarios.

---

## 2. Test layout

```
tests/unit/core/actions/move/
├── test_Vault__Sync__Move__Smoke.py              # basic happy path (covers brief 02 §6 cases 1-9)
├── test_Vault__Sync__Move__Object_IDs.py         # ID stability assertions
├── test_Vault__Sync__Move__Sentinel.py           # sentinel commit invariants
├── test_Vault__Sync__Move__Transaction.py        # failure-injection per step
├── test_Vault__Sync__Move__Markers.py            # key_generation + move-history.json
├── test_Vault__Sync__Move__Backup.py             # backup zip integrity + restore
├── test_Vault__Sync__Move__Tombstone.py          # old vault_id rejects writes after move (HTTP 403)
└── test_Vault__Sync__Move__Cleanup.py            # --cleanup after partial failure

tests/unit/network/api/
└── test_Vault__API__In_Memory__Tombstone.py      # tombstone simulation in the in-memory API

tests/unit/cli/
├── test_CLI__Vault__Move__Prompts.py             # the multi-step UX (mocking input() OK here — input mocking is allowed for prompt UX, no api/storage mocks)
└── test_CLI__Vault__Move__Dry_Run.py             # --dry-run performs no state change

tests/qa/sync/
└── test_Vault__Move__Multi_Round.py              # multi-round end-to-end scenarios (slow, qa-tier)
```

**Note on the dropped `Stale_Cache.py`:** earlier drafts of this brief included `test_Vault__Sync__Move__Stale_Cache.py` to verify a `key_generation`-driven cache invalidation in `pull`. That feature was dropped per Dinis 2026-05-06 (brief 02 §8b — `vault_id` always changes on move, so old clones naturally hit 404/403). Tests for the new tombstone-and-404 user-facing behaviour live in `test_Vault__Sync__Move__Tombstone.py` instead.

Mock policy: zero mocks for storage, crypto, API. Use `Vault__Test_Env` and a real local SG/Send instance fixture (already used by other qa tests). Input prompt mocking is acceptable in the CLI prompt tests because there's no realistic alternative for stdin emulation.

---

## 3. Unit-tier tests — the matrix

### 3a. `test_Vault__Sync__Move__Smoke.py`

The brief 00h §6 cases 1–9 live here. Cover the happy path and each prompt-driven variation. Expected size: ~12–15 tests.

### 3b. `test_Vault__Sync__Move__Object_IDs.py` — ID stability

The single most important invariant. Every test in this file follows the pattern:

```python
def test_<scenario>(self):
    # Setup: vault with N commits, M objects
    pre_ids = self._collect_all_object_ids(vault_dir)
    pre_refs = self._collect_all_refs(vault_dir)

    # Action: move
    self.sync.move(vault_dir, new_vault_key=..., target_api=..., reason='...')

    # Verify: object IDs identical except sentinel-related
    post_ids = self._collect_all_object_ids(vault_dir)
    post_refs = self._collect_all_refs(vault_dir)

    pre_set = set(pre_ids)
    post_set = set(post_ids)

    # Same set, except sentinel commit + sentinel parent ref are new
    new_objects = post_set - pre_set     # should be 1 new commit per active named branch
    lost_objects = pre_set - post_set    # should be 0 — old IDs preserved
    assert lost_objects == set(), f'object IDs vanished: {lost_objects}'
    assert len(new_objects) == self._n_active_branches(vault_dir)
```

Required scenarios:
1. Single-commit vault: pre=N objects, post=N+1 (only sentinel new).
2. Multi-commit vault (5 commits): same invariant.
3. Vault with 2 active named branches: 2 sentinels added; everything else preserved.
4. Vault with merge commits in history: merges' object IDs unchanged.
5. Vault with large blob (>4MB): large blob's ID unchanged after re-encryption.
6. Vault containing the migration sentinel commit (`tree-iv-determinism`): that historical sentinel's ID unchanged after move; a new `vault-move:` sentinel sits on top.

### 3c. `test_Vault__Sync__Move__Sentinel.py` — sentinel commit invariants

The sentinel commit is the only new object per branch. It's a load-bearing audit primitive. Tests:

1. `test_sentinel_message_format` — message contains `vault-move:`, `to vault-id <new>`, ISO timestamp, reason.
2. `test_sentinel_parent_is_old_head` — sentinel's parent is the pre-move HEAD of the same branch.
3. `test_sentinel_tree_unchanged` — sentinel's tree_id equals the parent commit's tree_id (no file changes; only metadata).
4. `test_sentinel_signed_by_new_branch_key` — verify under new key passes; verify under old key fails.
5. `test_sentinel_in_history_log` — `sgit history log` output (parsed) contains the sentinel as the new HEAD entry.
6. `test_sentinel_per_active_branch` — vault with 3 named branches gets 3 sentinels, one per branch, each correctly parented.
7. `test_sentinel_round_trip_via_pull` — fresh clone after move sees the sentinel and verifies it cleanly.

### 3d. `test_Vault__Sync__Move__Transaction.py` — failure injection per step

This is the safety-critical test file. **One test per workflow step**, injecting a failure mid-step and asserting the post-failure state is recoverable with zero data loss before step 7.

The test fixture exposes a `_break_at(step_name, exception_class)` helper that raises during the named step. After each test, assert:
- The user's working `.sg_vault/` directory is byte-identical to the pre-move snapshot.
- `.sg_vault_new/` is either absent (steps 1–4) or present-but-unused (steps 5–6).
- The target server has either no entry for the new vault-id (steps 1–4) or a partially-pushed entry that was cleaned up (steps 5–6).
- `sgit pull` and `sgit status` work correctly post-failure.
- The user can re-run `sgit vault move` cleanly.

Tests required:

1. `test_failure_in_step_1_validate_local` — inject corruption in head tree before move; assert clear error, no `.sg_vault_new/` created.
2. `test_failure_in_step_2_derive_keys` — simulate keygen failure; assert vault unchanged.
3. `test_failure_in_step_3_build_temp_vault_partway` — kill mid-re-encryption (e.g., 50% through). Assert `.sg_vault_new/` removable, original vault untouched.
4. `test_failure_in_step_4_write_sentinel` — inject signing-key load failure during sentinel write. Same assertions.
5. `test_failure_in_step_5_push_to_target` — point at a dead target API. Assert no half-pushed vault left on the (real test) source; `.sg_vault_new/` cleanable.
6. `test_failure_in_step_6_verify_target_mismatch` — after push, simulate a manual server-side tampering of the new vault. Verification fails. Assert recovery instructions surfaced.
7. `test_failure_in_step_7_backup_zip_disk_full` — fill the disk (or fixture-mock `os.statvfs`) so the zip write fails. Assert: nothing destructive happened yet (target vault exists on server but old vault still on source); user is prompted with "abort the move? [Y/n]".
8. `test_failure_in_step_8a_local_rename` — simulate `os.rename` failing during the final `.sg_vault → .sg_vault_old → .sg_vault_new → .sg_vault` swap. Assert: `.sg_vault/` and `.sg_vault_new/` both still on disk; old vault still live on source server (server delete hasn't run yet); user gets "rerun sgit vault move --cleanup" message.
9. `test_failure_in_step_8b_source_delete_after_local_rename` — simulate source-server delete API returning 500 after the local rename succeeded. Assert: local clone is on the new vault (rename completed); old vault still live on source. User gets "two valid vaults exist; run `sgit vault move --cleanup`" message; both vaults remain readable.
10. `test_step_8b_idempotent_when_old_vault_already_tombstoned` — run cleanup against a vault where the source delete previously succeeded (vault_id is tombstoned, returns 403). Assert cleanup treats the 403 as "already cleaned up", exits 0, doesn't raise.

### 3e. `test_Vault__Sync__Move__Markers.py` — key_generation + move-history

1. `test_key_generation_starts_at_1` — fresh vault has `key_generation = 1`.
2. `test_key_generation_increments_per_move` — after 1 move = 2, after 2 moves = 3.
3. `test_move_history_appends_per_move` — N moves → N records, all chained correctly with `from_vault_id == previous.to_vault_id`.
4. `test_move_history_round_trip` — `Schema__Vault_Moves.from_json(obj.json()).json() == obj.json()` after each move.
5. `test_move_history_includes_reason` — reason text from CLI flag is captured and round-trips.
6. `test_move_history_chain_integrity` — 3 sequential moves; assert chain is contiguous (no missing links, no orphan records).
7. `test_move_history_present_on_server` — after move, fetching the move-history from the target server matches the local copy.

### 3f. `test_Vault__Sync__Move__Backup.py` — backup zip

1. `test_backup_zip_exists_at_expected_path` — after move, `<dir>/.sg_vault/backups/<old-vault-id>__<ts>.zip` is present.
2. `test_backup_zip_contains_full_old_vault` — unzip into a temp directory; assert `bare/data/`, `bare/refs/`, `bare/indexes/`, `local/config.json` all present and byte-identical to the pre-move snapshot.
3. `test_backup_zip_excludes_vault_key_by_default` — assert `VAULT-KEY` is NOT in the zip when `--include-key=False`.
4. `test_backup_zip_includes_vault_key_when_opted_in` — assert `VAULT-KEY` IS in the zip when the user opted in via the prompt.
5. `test_backup_zip_sha256_sidecar` — `.sha256` file exists alongside the zip; running `sha256sum` against the zip matches the recorded value.
6. `test_backup_zip_restore_round_trip` — unzip into a fresh directory; with the OLD vault-key, decrypt a sample object; assert decryption succeeds and plaintext matches the original.
7. `test_backup_zip_restore_without_key_fails` — same setup but no key; decryption fails as expected. (Establishes that the zip alone without the key is not readable.)

### 3g. `test_Vault__Sync__Move__Tombstone.py` — old vault_id is permanently blocked

After a successful move, the old vault_id is tombstoned on the SG/Send server: any future write attempt returns HTTP 403. SGit must detect this and surface a friendly message.

1. `test_old_vault_id_rejects_writes_after_move` — perform a move; attempt to push to the OLD vault_id directly via the API; assert HTTP 403 raised.
2. `test_sgit_translates_403_to_friendly_message` — set up the same state; attempt a push at the SGit-CLI level; assert the user sees `"Vault {old_vault_id} has been permanently moved/deleted. Clone the new vault at {new_vault_id}."` rather than `"write key mismatch"`.
3. `test_old_vault_id_reads_return_not_found` — read attempts on tombstoned vault return `not_found`, not 403 (matches server spec). Verify SGit handles this distinct response correctly.
4. `test_in_memory_api_simulates_tombstone_correctly` — direct test of the `Vault__API__In_Memory` tombstone simulation against the documented behaviour: write→403, read→not_found, list→empty, second-delete→403.

### 3h. `test_Vault__Sync__Move__Cleanup.py` — --cleanup semantic

1. `test_cleanup_finishes_local_rename_after_8a_failure` — set up state with `.sg_vault_new/` present and `.sg_vault/` still on the old vault; run `sgit vault move --cleanup`; assert the rename completes atomically and the local clone ends up on the new vault.
2. `test_cleanup_finishes_server_delete_after_8b_failure` — local clone is on the new vault but the old vault still exists on source; run `sgit vault move --cleanup`; assert the source delete succeeds; assert old vault_id is now tombstoned.
3. `test_cleanup_is_idempotent_when_old_vault_already_tombstoned` — cleanup against an already-cleaned-up state; old vault returns 403 on delete; assert cleanup treats this as success, exits 0, doesn't raise or warn.
4. `test_cleanup_with_no_pending_move_errors_clearly` — run `--cleanup` on a vault with no `.sg_vault_new/` and no in-progress move-history record; assert "no pending move to clean up" message and exit code 1.

### 3i. `test_CLI__Vault__Move__Prompts.py` — UX (input() mocking allowed)

1. `test_all_yes_completes_move` — user answers Y to every prompt; move succeeds.
2. `test_no_at_step_1_aborts_clean` — user says N at the first prompt; assert no state change, exit code 1, clear "vault move cancelled" message.
3. `test_no_at_step_5_aborts_after_temp_built` — user builds the temp vault, then says N to push; assert `.sg_vault_new/` cleaned up, original vault intact.
4. `test_no_at_step_6_keeps_old_vault_on_server` — user says N to "delete old vault from server"; assert the new vault exists on target AND the old vault still exists on source. Test the "two-vault" follow-up message.
5. `test_edit_overrides_generated_key` — user types `edit`, then a custom new key; assert the move uses that custom key.
6. `test_edit_overrides_target_api_url` — same for target API.
7. `test_yes_flag_skips_all_prompts` — `--yes` flag set; assert all prompts skipped, all defaults used.
8. `test_dry_run_walks_steps_without_side_effects` — `--dry-run`; assert all 8 steps are walked logically, but no `.sg_vault_new/` created, no API calls, no backup zip.
9. `test_include_key_prompt_default_is_no` — assert the include-key prompt defaults to N; the move completes; the zip excludes `VAULT-KEY`.
10. `test_include_key_prompt_yes_includes_key` — explicit Y; zip contains `VAULT-KEY`.
11. `test_keep_backup_prompt_post_move_default_is_yes` — after successful move, the "keep backup zip?" prompt defaults to Y.
12. `test_delete_backup_requires_double_confirm` — user says n to "keep backup"; second prompt asks "are you sure?" with default N; user must explicitly confirm to delete.

---

## 4. QA-tier — multi-round move scenarios

These run against a real local SG/Send fixture, take longer, and live in `tests/qa/sync/test_Vault__Move__Multi_Round.py`. The qa tier already runs separately under the 80s gate; these add ~30s.

The core scenario uses **three sequential moves** to stress all the invariants together:

```
init vault V0  (keys K0, vault-id Vid0, server S0)
  ├─ commit "first" → C0a
  ├─ commit "second" → C0b
  └─ push → server S0 has V0

MOVE 1: in-place rotation
  vault move (new key K1, same server S0)
  → vault now V1 (vault-id Vid1) on S0
  → object IDs preserved
  → sentinel S1 added to HEAD
  → backup zip B1 written locally

  Assertions after MOVE 1:
    [a] sgit clone V1 with key K1 → succeeds, sees C0a, C0b, S1
    [b] sgit clone V0 with key K0 → fails ("vault not found"; old vault deleted)
    [c] B1 unzipped + decrypted with K0 → original V0 contents recovered
    [d] sgit commit "third" → succeeds, produces C1c
    [e] sgit push → succeeds
    [f] sgit history log → shows C0a, C0b, S1, C1c (in order)
    [g] sgit pull from a fresh clone → receives all four

MOVE 2: server move (no key rotation)
  vault move --to S1 (same key K1, new server S1)
  → vault now on S1 (vault-id Vid1 unchanged; key unchanged)
  → object IDs preserved
  → sentinel S2 added to HEAD
  → backup zip B2 written locally

  Assertions after MOVE 2:
    [a] sgit clone Vid1 from S1 with key K1 → succeeds, sees C0a, C0b, S1, C1c, S2
    [b] sgit clone Vid1 from S0 → fails (deleted from S0)
    [c] sgit commit "fourth" → C2d, push to S1 succeeds
    [d] history log shows the full chain in order

MOVE 3: rotation + server move combined
  vault move --new-key K3 --to S0 (different key, back to original server)
  → vault now V3 on S0 (new vault-id Vid3, new key K3)
  → object IDs preserved
  → sentinel S3 added
  → backup zip B3 written locally

  Assertions after MOVE 3:
    [a] sgit clone Vid3 from S0 with K3 → full history visible (6 commits + 3 sentinels = 9 entries)
    [b] all clone modes work: clone, clone-branch, clone-headless, clone-range
    [c] sgit migrate status → records show vault has been moved 3 times
    [d] move-history.json on disk has 3 records, correctly chained
    [e] each backup zip is independently restorable with its corresponding key (K0 for B1, K1 for B2, K2 for B3)
    [f] sgit fetch on S0 works
    [g] sgit pull on S0 works
    [h] sgit share/publish on the moved vault works
```

Tests in this file:

1. `test_three_sequential_moves_preserve_history` — the scenario above end-to-end.
2. `test_each_move_increments_key_generation` — after 3 moves, `key_generation == 4`.
3. `test_move_history_chain_after_three_moves` — 3 chained records, no orphans.
4. `test_each_backup_independently_restorable` — unzip B1, B2, B3 separately; each with its corresponding old key reads its corresponding pre-move state.
5. `test_object_ids_stable_across_three_moves` — captures the full ID set before MOVE 1, after MOVE 1, after MOVE 2, after MOVE 3. Assertion: all old IDs survive every move; only sentinels add new IDs.
6. `test_decryption_matrix_old_keys_dont_read_new_vault` — a 3×3 matrix of (key, vault-id, server) combinations. Only matched triples succeed.
7. `test_clone_each_mode_after_third_move` — clone, clone-branch, clone-headless, clone-range all work on the V3 vault.
8. `test_pull_after_third_move_from_a_pre_first_move_clone_fails_clearly` — set up a sparse clone B pointing at Vid0 from before MOVE 1. After MOVE 3, Vid0 is tombstoned on its server. Run `sgit pull` on B. Assert: pull fails with the friendly "vault has been moved/deleted" message (not a raw 403/404). User's recovery path is to clone V3 fresh — there is NO automatic key adoption.
9. `test_history_log_across_moves_shows_all_sentinels` — `sgit history log` after MOVE 3 shows S1, S2, S3 inline with the user commits.
10. `test_failed_move_2_leaves_v1_intact` — perform MOVE 1 successfully; attempt MOVE 2 with a target server that fails; assert V1 is unchanged on S0; assertions [a]–[g] from MOVE 1 still hold.

---

## 5. Verification / acceptance

When all the above tests pass:

- **3,260+ unit tests** (3,246 current + the new test files; expect ~50 new unit tests).
- **140+ qa tests** (128 current + ~12 new qa tests for multi-round).
- All run green under the existing CI configuration. No mocks introduced for storage/api/crypto; only `input()` mocked in the prompt tests.
- The full unit run completes within 360s; the qa tier completes within the existing 80s gate (these tests add ~30s).

Add coverage for `sgit_ai/core/actions/move/` to the standard `pytest --cov` target. **Move-related code must hit ≥95% line coverage** because the destructive nature of the operation makes uncovered branches especially dangerous.

---

## 6. Out of scope for this testing brief

- **Vault web team JS tests** — covered in the separate web debrief mentioned in `00h §9`. Don't write JS tests in this CLI repo.
- **Cross-version move** (a v0.14 vault moved to a v0.15 client) — single-version testing only for now; cross-version compatibility becomes a concern when v0.15 lands.
- **Performance benchmarks** — record timings if they're cheap (the qa multi-round test will naturally measure 3 moves end-to-end), but no formal perf-regression suite. Add later if move performance becomes a complaint.
- **Adversarial / fuzzing tests on the move workflow** — defer to a future security pass. The functional tests in this brief plus the existing AppSec discipline are sufficient for v1.

---

## 7. Test execution order during development

The executor should write tests in this order, landing each as a separate commit alongside the corresponding implementation slice:

1. **Object-ID stability tests (3b)** — write FIRST, against the implementation as it lands. These tests catch the most fundamental class of bugs.
2. **Markers tests (3e)** — written next; key_generation + move-history are simple and well-isolated.
3. **Sentinel tests (3c)** — verify the audit primitive works correctly.
4. **Backup tests (3f)** — verify the recovery primitive.
5. **Smoke (3a)** — the integration glue.
6. **Transaction failure-injection (3d)** — once the happy path works.
7. **Stale cache (3g)** — once markers are reliable.
8. **Tombstone (3g)** + **Cleanup (3h)** — once transaction tests prove failure modes are recoverable; verify the recovery primitives (`--cleanup`, tombstone-aware error messages) work end-to-end.
9. **Prompts (3i)** — once `cmd_vault_move` exists in CLI__Vault.
10. **Multi-round qa (§4)** — last; it's the integration capstone.

Each commit message: `test(vault-move): <area> — <test count> tests`.

Reviewer Fix passes after each commit per the existing pattern.
