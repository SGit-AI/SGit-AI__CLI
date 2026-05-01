# M00 — Adversarial Mutation Matrix (Planned + Status)

**Status:** all 10 mutations are PLANNED and documented (none executed live
in this analysis phase, per Villager rules — Architect/QA execute in
Phase 3). For each, predicted detection and the missing-test gap is recorded.

## Legend

- **D** = currently detected by existing test (mutation should make a test
  fail).
- **U** = undetected — mutation slips through; missing test gap noted.
- **P** = partial — some assertions catch some mutations; recommended
  hardening test added.

| # | Mutation | Target File:Line | Status | Existing Test | Recommended New Test |
|---|----------|------------------|--------|---------------|----------------------|
| M1 | Replace `hmac.new(key, plaintext, sha256)` with `hashlib.sha256(plaintext)` in `encrypt_deterministic` (drops the HMAC key) | `Vault__Crypto.py:169` | **U** | None — no test exercises `encrypt_deterministic` directly | Cross-vault tree-id divergence test: two vaults with same plaintext must produce different tree-ids |
| M2 | Hard-code HMAC key to constant in `encrypt_deterministic` | `Vault__Crypto.py:169` | **U** | None | Same as M1 |
| M3 | Replace `iv = hmac(...)` with `iv = os.urandom(12)` (breaks determinism) | `Vault__Crypto.py:169` | **P** | `test_Vault__Sub_Tree` round-trips function but does not assert tree-id determinism | Same-input → same-tree-id property test |
| M4 | In `rekey_wipe`, replace `shutil.rmtree(sg_dir)` with `pass` | `Vault__Sync.py:1770` | **D** | `test_rekey_wipe_removes_objects` asserts `not os.path.isdir(sg_dir)` after wipe (line 195) | None additional |
| M5 | In `_pbkdf2_cached`, set `maxsize=0` (disable cache) | `Vault__Crypto.py:26` | **D** | `test_pbkdf2_cache_size_bounded` asserts `info.maxsize == 256` and `info.currsize == n` — both fail when `maxsize=0` | Closed by brief 12 (2026-05-01) |
| M6 | In `clone_mode.json` write path, omit `read_key` field | `Vault__Sync.py:1550, 1654` | **D** | `test_Vault__Sync__Multi_Clone` reads back the read-only clone — would fail decrypt | Add explicit `assert 'read_key' in clone_mode_data` for fast diagnostic |
| M7 | In `write_file`, replace `crypto.encrypt(read_key, file_content)` with `file_content` (no encryption) | `Vault__Sync.py:282` | **U** | `test_written_file_appears_on_disk` checks working dir, NOT `bare/data/` ciphertext | `test_write_file_blob_is_encrypted` — open `bare/data/{blob_id}` and assert plaintext NOT present |
| M8 | In `_save_push_state`, add `'paths': flat_map` field | `Vault__Sync.py:2742-2744` | **U** | No test inspects `push_state.json` content | `test_push_state_only_safe_fields` (schema allowlist) |
| M9 | In `probe_token` success path, write `clone_mode.json` (or any disk artefact) | `Vault__Sync.py:1820, 1830` | **U** | No test asserts probe leaves no disk state | `test_probe_writes_no_disk_artefacts` |
| M10 | In `Vault__API.delete_vault`, drop the `x-sgraph-vault-write-key` header | `Vault__API.py:209-210` | **U** (in-memory tests) | In-memory API ignores the header anyway | Real-server integration test: `test_delete_vault_requires_write_key` (Phase 3, against `sgraph-ai-app-send`) |

## Baseline Mutations (from role doc — already covered briefly)

| #  | Mutation | Predicted Status |
|----|----------|------------------|
| B1 | `PBKDF2_ITERATIONS = 1000` | **D** by `test_pbkdf2_iterations_constant` |
| B2 | `AES_KEY_BYTES = 16` | **D** by `test_aes_key_bytes_constant` |
| B3 | Change `HKDF_INFO_PREFIX` byte-string | **U** — no test asserts the constant value (only that derived key length is 32). Recommend `test_hkdf_info_prefix_constant`. |
| B4 | Remove vault_key validation (`VAULT_ID_PATTERN`) | **D** by various init/parse tests using invalid ids |
| B5 | Skip blob encryption in push (`bid = bid; ciphertext = plaintext`) | **D** by `test_AppSec__No_Plaintext_In_Object_Store` |

## Net Coverage

- **Detected today:** 5 of 10 (M4, M5, M6, plus baseline B1/B2/B4/B5 which are
  not in the new mutation list but worth noting). M5 closed by brief 12 (2026-05-01).
- **Undetected today:** 5 of 10 (M1, M2, M7, M8, M9, M10).
- **Partial:** 1 (M3).

This is a **substantial test gap** for v0.10.30's new attack surface.

## Suggested Phase-3 Order

1. **High value** — M1, M2, M7 (cross-vault leakage + write_file encryption
   integrity). One PR, three tests.
2. **Medium** — M8, M9 (filesystem-content allowlists). One PR.
3. **Lower** — M3, M5 (determinism, cache bound). One PR.
4. **Real-server** — M10 (auth header). DevOps + QA integration.

Total estimated effort for closing the gap: ~6 hours of test-writing.

## Live-Run Note

Per role rules, no mutations were executed live during this analysis phase.
All status entries above are predicted from code reading and existing test
inspection. QA Phase 3 should run each mutation, observe the test output,
and write the missing test before reverting.
